"""`JohansenBasketAdapter` (docs/14 sleeve D, v4): basket cointegration via
the Johansen procedure -- a genuinely different formulation from the
2-instrument OLS-hedge (`StatsmodelsPairsAdapter`) and distance-method
(`stat_arb_adapter.DistancePairsAdapter`) pairs above it, since it estimates
a cointegrating *vector* across an arbitrary-size basket (self + N other
symbols) rather than a single fixed hedge ratio against one partner.

`statsmodels` (BSD-3) is kept in the optional `models` extra, not the base
runtime (`pyproject.toml`) -- imported lazily here so a base install never
needs it, and a missing install quarantines cleanly at intake instead of
crashing (same pattern as `StatsmodelsPairsAdapter`).

Needs the engine's multi-symbol `Context.universe_closes`/`Session`
extension (docs/14 v4): per-symbol close history is built directly from the
raw `MarketEvent`s this adapter observes -- including other symbols' bars
-- exactly like `CrossSectionalAdapter` (sleeve C). A decision is only ever
made (and only ever acted on) on this adapter's own symbol's bar.

Every rolling `window`, re-estimates the Johansen cointegrating vector on
log-prices of `[symbol, *basket]`, forms the implied stationary combination
series, and trades *its* z-score: long when the combination is cheap
(deeply negative z), flat once it reverts. If a window is numerically
degenerate (e.g. a near-singular sample covariance), the bar is skipped
rather than raising -- an honest "insufficient signal this bar," not a
crash.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


def _import_coint_johansen() -> object:
    try:
        from statsmodels.tsa.vector_ar.vecm import coint_johansen
    except ImportError as exc:
        raise ImportError(
            "JohansenBasketAdapter requires the optional 'models' extra: "
            "pip install '.[models]'"
        ) from exc
    return coint_johansen


def _zscore(series: Sequence[float]) -> float | None:
    n = len(series)
    mean = sum(series) / n
    variance = sum((s - mean) ** 2 for s in series) / n
    std = variance**0.5
    if std == 0:
        return None
    return float((series[-1] - mean) / std)


class JohansenBasketAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        basket: Sequence[Symbol],
        window: int = 90,
        det_order: int = 0,
        k_ar_diff: int = 1,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
    ) -> None:
        if symbol in basket:
            raise ValueError("symbol must not be a member of its own basket")
        if len(basket) < 1:
            raise ValueError("basket must contain at least one other symbol")
        self._coint_johansen = _import_coint_johansen()
        self.name = name
        self.params: dict[str, object] = {
            "window": window, "det_order": det_order, "k_ar_diff": k_ar_diff,
            "entry_z": entry_z, "exit_z": exit_z,
        }
        self._symbol = symbol
        self._basket = list(basket)
        self._window = window
        self._det_order = det_order
        self._k_ar_diff = k_ar_diff
        self._entry_z = entry_z
        self._exit_z = exit_z
        self._history: dict[Symbol, list[float]] = {symbol: [], **{sym: [] for sym in basket}}
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        for sym in self._history:
            self._history[sym] = []
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol not in self._history:
            return []
        self._history[ev.symbol].append(float(ev.c))
        if ev.symbol != self._symbol:
            return []

        if len(self._history[self._symbol]) < self._window or any(
            len(self._history[sym]) < self._window for sym in self._basket
        ):
            return []

        z = self._combination_zscore()
        if z is None:
            return []

        target: Literal["LONG", "FLAT"] | None = None
        if z <= -self._entry_z:
            target = "LONG"
        elif z >= self._exit_z:
            target = "FLAT"
        if target is None or target == self._position:
            return []

        self._position = target
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction=target,
                strength=1.0 if target == "LONG" else 0.0,
                intent_kind="ENTER" if target == "LONG" else "EXIT",
                bar_ts=ev.ts_open,
                reason=(
                    f"{self.name}: Johansen basket combination z={z:.2f} "
                    f"over {len(self._basket)}-symbol basket"
                ),
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None

    def _combination_zscore(self) -> float | None:
        symbols = [self._symbol, *self._basket]
        levels = np.array(
            [self._history[sym][-self._window :] for sym in symbols], dtype=np.float64
        ).T
        log_levels = np.log(levels)
        try:
            result = self._coint_johansen(  # type: ignore[operator]
                log_levels, self._det_order, self._k_ar_diff
            )
            weights = np.real(result.evec[:, 0])
        except (np.linalg.LinAlgError, ValueError):
            return None  # a numerically degenerate window -- skip, don't crash
        combination = log_levels @ weights
        return _zscore(combination.tolist())
