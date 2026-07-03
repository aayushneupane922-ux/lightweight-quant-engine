"""Shared plumbing for the three portfolio/risk-allocation adapters
(`PyPortfolioOptAdapter`, `SkfolioOptimizerAdapter`, `RiskfolioAdapter`).

Those libraries all optimize a *weight vector* over a multi-instrument
universe; the current engine is single-instrument (multi-instrument
accounting is docs/10 M11 scope). Rather than fake a multi-asset book, each
adapter here does one real, deterministic optimization over the supplied
`universe_closes` at `on_start` and projects only the tracked `symbol`'s
own weight onto a static LONG/FLAT target for this backtest — an honest,
declared simplification (see each adapter's `failure_modes`), not a full
rebalancing portfolio.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol

WeightFn = Callable[[Mapping[Symbol, Sequence[float]]], Mapping[Symbol, float]]


class StaticWeightProjectionAdapter:
    """Runs `weight_fn(universe_closes)` once at `on_start`, then emits a
    single ENTER/EXIT to match whatever LONG/FLAT that implies for
    `symbol` (weight > `min_weight` -> LONG, else FLAT)."""

    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        universe_closes: Mapping[Symbol, Sequence[float]],
        weight_fn: WeightFn,
        min_weight: float = 0.0,
        params: dict[str, object] | None = None,
    ) -> None:
        if symbol not in universe_closes:
            raise ValueError(f"{symbol!r} must be included in universe_closes")
        self.name = name
        self.params: dict[str, object] = dict(params or {})
        self._symbol = symbol
        self._universe_closes = universe_closes
        self._weight_fn = weight_fn
        self._min_weight = min_weight
        self._target: Literal["LONG", "FLAT"] = "FLAT"
        self._position: Literal["FLAT", "LONG"] = "FLAT"
        self._emitted = False

    def on_start(self, ctx: Context) -> None:
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"
        self._emitted = False
        weights = self._weight_fn(self._universe_closes)
        self._target = "LONG" if weights.get(self._symbol, 0.0) > self._min_weight else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol or self._emitted:
            return []
        self._emitted = True
        if self._target == self._position:
            return []
        self._position = self._target
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction=self._target,
                strength=1.0 if self._target == "LONG" else 0.0,
                intent_kind="ENTER" if self._target == "LONG" else "EXIT", bar_ts=ev.ts_open,
                reason=f"{self.name}: static optimized weight -> {self._target}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
