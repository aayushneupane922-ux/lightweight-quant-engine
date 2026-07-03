"""`ChangePointAdapter` (docs/03 §3.2, family: regime). `ruptures` (BSD-2)
is kept in the optional `models` extra, not the base runtime — imported
lazily so a base install never needs it, and a missing install quarantines
cleanly at intake instead of crashing.

Runs offline change-point detection (`ruptures`, deterministic) over the
trailing return series every `refit_every` bars, then trades the *most
recent* segment: long while the last segment's mean return is positive,
flat otherwise. Adapts to structural breaks without curve-fitting a price
level.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


def _import_ruptures() -> object:
    try:
        import ruptures
    except ImportError as exc:
        raise ImportError(
            "ChangePointAdapter requires the optional 'models' extra: pip install '.[models]'"
        ) from exc
    return ruptures


class ChangePointAdapter:
    def __init__(
        self, *, symbol: Symbol, name: str, window: int = 120, refit_every: int = 10,
        penalty: float = 3.0,
    ) -> None:
        self._rpt = _import_ruptures()
        self.name = name
        self.params: dict[str, object] = {
            "window": window, "refit_every": refit_every, "penalty": penalty,
        }
        self._symbol = symbol
        self._window = window
        self._refit_every = refit_every
        self._penalty = penalty
        self._closes: list[float] = []
        self._position: Literal["FLAT", "LONG"] = "FLAT"
        self._bars_since_fit = 0
        self._last_target: Literal["LONG", "FLAT"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        self._closes.clear()
        self._bars_since_fit = 0
        self._last_target = "FLAT"
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        self._closes.append(float(ev.c))
        if len(self._closes) < self._window + 1:
            return []

        self._bars_since_fit += 1
        if self._bars_since_fit >= self._refit_every:
            self._bars_since_fit = 0
            tail = np.array(self._closes[-(self._window + 1) :])
            returns = np.diff(tail) / tail[:-1]
            algo = self._rpt.Pelt(model="rbf").fit(returns)  # type: ignore[attr-defined]
            breaks = algo.predict(pen=self._penalty)
            start = breaks[-2] if len(breaks) >= 2 else 0
            last_segment_mean = float(np.mean(returns[start:]))
            self._last_target = "LONG" if last_segment_mean > 0 else "FLAT"

        if self._last_target == self._position:
            return []
        self._position = self._last_target
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction=self._last_target,
                strength=1.0 if self._last_target == "LONG" else 0.0,
                intent_kind="ENTER" if self._last_target == "LONG" else "EXIT",
                bar_ts=ev.ts_open,
                reason=f"{self.name}: last-segment regime -> {self._last_target}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
