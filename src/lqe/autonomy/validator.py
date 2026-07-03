"""The `Validator`: walk-forward + cost sweep + benchmarks + DSR (docs/04
§4.1, docs/archive/09). Produces the evidence a `PromotionGate` judges —
the Validator never decides PASS/FAIL itself (docs/11 §11.6: only the
`PromotionGate` may set a verdict).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from lqe.analytics.dsr import deflated_sharpe_ratio
from lqe.analytics.metrics import returns_from_equity, sharpe_ratio
from lqe.backtest.runner import run_backtest
from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol
from lqe.models.base import Strategy

_FROZEN = ConfigDict(frozen=True)


class PromotionCandidate(BaseModel):
    model_config = _FROZEN

    candidate_id: str
    model_id: str
    params: dict[str, Any]
    book: Literal["sandbox"]
    hypo_id: str
    study_id: str
    data_version: str
    seed: int
    n_trials_context: int


class ValidationResult(BaseModel):
    model_config = _FROZEN

    walk_forward_oos_sharpe: float
    dsr: float
    pbo: float
    cost_survived: bool
    beats_equal_weight: bool
    beats_random: bool
    n_trades: int
    evidence: dict[str, Any]


class _RandomEntryStrategy:
    """The random-entry control (docs/archive/09 §9.5): same instrument,
    same trade count, random timing — the minimum bar a real signal must
    clear."""

    name = "random_entry_control"
    params: dict[str, object] = {}

    def __init__(
        self, *, symbol: Symbol, n_bars: int, target_trades: int, hold_bars: int, seed: int
    ) -> None:
        self._symbol = symbol
        self._position: Literal["FLAT", "LONG"] = "FLAT"
        self._bar_idx = -1
        rng = np.random.default_rng(seed)
        hold_bars = max(1, hold_bars)
        latest_entry = max(1, n_bars - hold_bars)
        candidates = list(range(latest_entry))
        rng.shuffle(candidates)
        chosen = sorted(candidates[: max(0, target_trades)])
        self._entry_bars = set(chosen)
        self._exit_bars = {b + hold_bars for b in chosen}

    def on_start(self, ctx: Context) -> None:
        self._bar_idx = -1
        self._position = "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        self._bar_idx += 1
        if self._bar_idx in self._entry_bars and self._position == "FLAT":
            self._position = "LONG"
            return [
                SignalEvent(
                    strategy=self.name, symbol=self._symbol, direction="LONG", strength=1.0,
                    intent_kind="ENTER", bar_ts=ev.ts_open, reason="random-entry control",
                )
            ]
        if self._bar_idx in self._exit_bars and self._position == "LONG":
            self._position = "FLAT"
            return [
                SignalEvent(
                    strategy=self.name, symbol=self._symbol, direction="FLAT", strength=0.0,
                    intent_kind="EXIT", bar_ts=ev.ts_open, reason="random-entry control",
                )
            ]
        return []

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None


class Validator:
    def __init__(
        self,
        *,
        cost_sweep_bps: Sequence[float] = (0.0, 5.0, 10.0, 20.0),
        survival_bps: float = 10.0,
        n_folds: int = 4,
        random_control_reps: int = 20,
        periods_per_year: float = 365.0 * 24.0 * 60.0,  # 1-minute bars, 24/7 crypto
    ) -> None:
        self._cost_sweep_bps = cost_sweep_bps
        self._survival_bps = survival_bps
        self._n_folds = n_folds
        self._random_control_reps = random_control_reps
        self._periods_per_year = periods_per_year

    def validate(
        self,
        candidate: PromotionCandidate,
        *,
        bars: Sequence[MarketEvent],
        symbol: Symbol,
        strategy_factory: Callable[[], Strategy],
        starting_cash: Decimal,
    ) -> ValidationResult:
        stitched_returns, n_trades = self._walk_forward(
            bars=bars, symbol=symbol, strategy_factory=strategy_factory, starting_cash=starting_cash
        )
        wf_sharpe = sharpe_ratio(stitched_returns, periods_per_year=self._periods_per_year)
        dsr = deflated_sharpe_ratio(stitched_returns, n_trials=max(1, candidate.n_trials_context))

        cost_survival = self._cost_sweep(
            bars=bars, symbol=symbol, strategy_factory=strategy_factory, starting_cash=starting_cash
        )
        cost_survived = cost_survival.get(self._survival_bps, 0.0) > 0.0

        full_session = run_backtest(
            run_id=f"validate:{candidate.candidate_id}:full", symbol=symbol, bars=bars,
            strategy=strategy_factory(), starting_cash=starting_cash,
        )
        candidate_returns = returns_from_equity(full_session.equity_curve)
        candidate_sharpe = sharpe_ratio(candidate_returns, periods_per_year=self._periods_per_year)

        buy_hold_sharpe = self._buy_hold_sharpe(bars)
        # Single-model catalog (M6 adds more): buy-and-hold is the honest
        # proxy for "beats equal-weight" until there's more than one model
        # to equal-weight against.
        beats_equal_weight = candidate_sharpe > buy_hold_sharpe

        random_sharpes = self._random_control_sharpes(
            bars=bars,
            symbol=symbol,
            n_trades=len(full_session.trade_pnls),
            starting_cash=starting_cash,
        )
        beats_random = (
            candidate_sharpe > float(np.mean(random_sharpes)) if random_sharpes else False
        )

        evidence: dict[str, Any] = {
            "cost_sweep_sharpe_by_bps": cost_survival,
            "candidate_full_sample_sharpe": candidate_sharpe,
            "buy_hold_sharpe": buy_hold_sharpe,
            "random_control_sharpes": random_sharpes,
            "random_control_mean_sharpe": float(np.mean(random_sharpes)) if random_sharpes else 0.0,
            "n_folds": self._n_folds,
            "n_trials_context": candidate.n_trials_context,
        }

        return ValidationResult(
            walk_forward_oos_sharpe=wf_sharpe,
            dsr=dsr,
            pbo=0.0,  # not applicable with a single candidate; see analytics/pbo.py
            cost_survived=cost_survived,
            beats_equal_weight=beats_equal_weight,
            beats_random=beats_random,
            n_trades=n_trades,
            evidence=evidence,
        )

    def _walk_forward(
        self,
        *,
        bars: Sequence[MarketEvent],
        symbol: Symbol,
        strategy_factory: Callable[[], Strategy],
        starting_cash: Decimal,
    ) -> tuple[np.ndarray, int]:
        fold_size = max(1, len(bars) // self._n_folds)
        stitched: list[np.ndarray] = []
        n_trades = 0
        for i in range(self._n_folds):
            start = i * fold_size
            end = len(bars) if i == self._n_folds - 1 else (i + 1) * fold_size
            fold_bars = bars[start:end]
            if len(fold_bars) < 2:
                continue
            session = run_backtest(
                run_id=f"walk-forward:fold-{i}", symbol=symbol, bars=fold_bars,
                strategy=strategy_factory(), starting_cash=starting_cash,
            )
            stitched.append(returns_from_equity(session.equity_curve))
            n_trades += len(session.trade_pnls)
        if not stitched:
            return np.array([]), 0
        return np.concatenate(stitched), n_trades

    def _cost_sweep(
        self,
        *,
        bars: Sequence[MarketEvent],
        symbol: Symbol,
        strategy_factory: Callable[[], Strategy],
        starting_cash: Decimal,
    ) -> dict[float, float]:
        results: dict[float, float] = {}
        for bps in self._cost_sweep_bps:
            session = run_backtest(
                run_id=f"cost-sweep:{bps}", symbol=symbol, bars=bars, strategy=strategy_factory(),
                starting_cash=starting_cash, slippage_bps=bps, commission_bps=bps,
            )
            returns = returns_from_equity(session.equity_curve)
            results[bps] = sharpe_ratio(returns, periods_per_year=self._periods_per_year)
        return results

    def _buy_hold_sharpe(self, bars: Sequence[MarketEvent]) -> float:
        if len(bars) < 2:
            return 0.0
        closes = np.array([float(bar.c) for bar in bars])
        with np.errstate(divide="ignore", invalid="ignore"):
            returns = np.diff(closes) / closes[:-1]
        returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)
        return sharpe_ratio(returns, periods_per_year=self._periods_per_year)

    def _random_control_sharpes(
        self, *, bars: Sequence[MarketEvent], symbol: Symbol, n_trades: int, starting_cash: Decimal
    ) -> list[float]:
        if n_trades <= 0 or len(bars) < 2:
            return []
        hold_bars = max(1, len(bars) // max(1, n_trades * 2))
        sharpes: list[float] = []
        for rep in range(self._random_control_reps):
            strategy = _RandomEntryStrategy(
                symbol=symbol,
                n_bars=len(bars),
                target_trades=n_trades,
                hold_bars=hold_bars,
                seed=rep,
            )
            session = run_backtest(
                run_id=f"random-control:{rep}", symbol=symbol, bars=bars, strategy=strategy,
                starting_cash=starting_cash,
            )
            returns = returns_from_equity(session.equity_curve)
            sharpes.append(sharpe_ratio(returns, periods_per_year=self._periods_per_year))
        return sharpes
