"""`CrossSectionalAdapter` (docs/14 sleeve C, v4): ranks a fixed universe of
symbols each bar and goes long only when this adapter's own `symbol` is in
the top quantile by score -- a genuinely different return driver from the
single-instrument sleeves (trend/momentum, mean-reversion, ...), since the
decision depends on *relative* standing across a universe, not this
instrument's own price path in isolation.

Needs the engine's multi-symbol `Context.universe_closes`/`Session`
extension (docs/14 v4): a per-symbol close history is built directly from
the raw `MarketEvent`s this adapter observes -- including *other* symbols'
bars, which `Session.run` now feeds to every strategy's `on_market` (see
`backtest/make_session.py`). A decision is only ever made (and only ever
acted on) on this adapter's *own* symbol's bar, matching the engine's
no-look-ahead, one-book-per-session guarantee.

Long-only, never short: this catalog's other native strategies are all
long/flat, and the engine's short-selling path (sizing/risk/accounting for
a negative position) has never actually been exercised by any model here.
The textbook "long top / short bottom" cross-sectional design is
deliberately simplified to "long the top quantile, flat otherwise" rather
than reaching for an untested short path -- an honest simplification,
declared in the manifest's `failure_modes`, not a silent one.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol

Metric = Literal["momentum", "reversal", "low_vol", "residual_momentum"]


def _momentum_score(history: Sequence[float], lookback: int) -> float:
    return (history[-1] - history[-lookback - 1]) / history[-lookback - 1]


def _reversal_score(history: Sequence[float], lookback: int) -> float:
    # the mirror image of momentum: a recent underperformer scores highest,
    # betting on a short-term bounce rather than continuation.
    return -_momentum_score(history, lookback)


def _low_vol_score(history: Sequence[float], lookback: int) -> float:
    tail = history[-lookback:]
    returns = [(b - a) / a for a, b in zip(tail, tail[1:])]  # noqa: B905 - deliberately uneven
    if not returns:
        return float("-inf")
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    # lower realized vol -> higher score (the calmest instrument ranks top).
    return -float(variance**0.5)


_SCORE_FNS = {
    "momentum": _momentum_score,
    "reversal": _reversal_score,
    "low_vol": _low_vol_score,
}


class CrossSectionalAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        universe: Sequence[Symbol],
        lookback: int = 20,
        top_quantile: float = 0.5,
        metric: Metric = "momentum",
    ) -> None:
        if symbol not in universe:
            raise ValueError(f"{symbol!r} must be included in its own ranking universe")
        if not 0.0 < top_quantile <= 1.0:
            raise ValueError("top_quantile must be in (0, 1]")
        self.name = name
        self.params: dict[str, object] = {
            "lookback": lookback, "top_quantile": top_quantile, "metric": metric,
        }
        self._symbol = symbol
        self._universe = list(universe)
        self._lookback = lookback
        self._top_quantile = top_quantile
        self._metric = metric
        self._history: dict[Symbol, list[float]] = {sym: [] for sym in self._universe}
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        for sym in self._universe:
            self._history[sym] = []
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol not in self._history:
            return []  # a bar for a symbol outside our declared universe
        self._history[ev.symbol].append(float(ev.c))
        if ev.symbol != self._symbol:
            return []  # observe other symbols; only ever act on our own bar

        target = self._target_state()
        if target is None or target == self._position:
            return []
        if target == "LONG":
            self._position = "LONG"
            return [
                SignalEvent(
                    strategy=self.name, symbol=self._symbol, direction="LONG", strength=1.0,
                    intent_kind="ENTER", bar_ts=ev.ts_open,
                    reason=f"{self.name}: top {self._top_quantile:.0%} by {self._metric}",
                )
            ]
        self._position = "FLAT"
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction="FLAT", strength=0.0,
                intent_kind="EXIT", bar_ts=ev.ts_open,
                reason=f"{self.name}: no longer top {self._top_quantile:.0%} by {self._metric}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None

    def _target_state(self) -> Literal["LONG", "FLAT"] | None:
        if any(len(self._history[sym]) < self._lookback + 1 for sym in self._universe):
            return None  # not enough history for the whole universe yet
        scores = self._scores()
        ranked = sorted(self._universe, key=lambda sym: scores[sym], reverse=True)
        cutoff = max(1, int(len(ranked) * self._top_quantile))
        return "LONG" if self._symbol in ranked[:cutoff] else "FLAT"

    def _scores(self) -> dict[Symbol, float]:
        if self._metric == "residual_momentum":
            raw = {
                sym: _momentum_score(self._history[sym], self._lookback) for sym in self._universe
            }
            mean = sum(raw.values()) / len(raw)
            return {sym: value - mean for sym, value in raw.items()}
        score_fn = _SCORE_FNS[self._metric]
        return {sym: score_fn(self._history[sym], self._lookback) for sym in self._universe}
