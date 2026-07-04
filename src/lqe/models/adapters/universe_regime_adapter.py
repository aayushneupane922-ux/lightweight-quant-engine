"""`UniverseRegimeGateAdapter` (docs/15 V5 M28 "Wake the Sleeves"): a
universe-wide regime overlay, distinct from this catalog's existing
single-instrument regime models (`HmmRegimeAdapter`/`ChangePointAdapter`/
`vol_regime_gate`, all of which read only their own symbol's price path).
This one reads the whole universe's average pairwise return correlation to
decide whether the market is in an "idiosyncratic" regime (instruments
moving mostly independently -- normal conditions for a single-instrument
trend model to operate in) or a "systemic" one (everything moving together,
usually a risk-off/correlation-spike event) and gates a simple trend entry
on its own symbol accordingly.

Same "switch sleeves, not standalone alpha" philosophy as this catalog's
other regime overlays (docs/14 sleeve I) -- it is not itself a return
driver, it is a risk-off brake on one. Tagged with the existing
`regime_overlay` sleeve rather than a new `Sleeve` literal: it is still
philosophically a regime overlay, just scoped to the universe instead of
one instrument.

Needs a genuinely interleaved multi-symbol bar stream to ever compute a
correlation (built the same way `CrossSectionalAdapter`/`DistancePairsAdapter`
already do: a per-symbol close history accumulated directly from every
observed `MarketEvent`, including siblings' bars, that this engine's
`Session.run()`/`LiveMultiModelRunner.process_bar` already broadcast to
every strategy) -- inert (no signal) until every universe symbol has enough
history, same "insufficient real data -> honestly absent" pattern as the
rest of this milestone's sleeves.

Long-only, never short, same simplification as every other native model in
this catalog.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


def _returns(history: Sequence[float]) -> list[float]:
    return [(b - a) / a for a, b in zip(history, history[1:], strict=False)]


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    denom = (var_a * var_b) ** 0.5
    if denom == 0:
        return 0.0
    return float(cov / denom)


class UniverseRegimeGateAdapter:
    """Gates a simple own-symbol trend entry on the universe's average
    pairwise return correlation: LOW correlation (idiosyncratic regime) ->
    trade the trend normally; HIGH correlation (systemic/risk-off regime) ->
    stay flat, regardless of what the trend itself says."""

    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        universe: Sequence[Symbol],
        corr_lookback: int = 20,
        corr_threshold: float = 0.5,
        trend_lookback: int = 10,
    ) -> None:
        if symbol not in universe:
            raise ValueError(f"{symbol!r} must be included in its own regime universe")
        others = [sym for sym in universe if sym != symbol]
        if len(others) < 2:
            raise ValueError(
                "UniverseRegimeGateAdapter needs at least 2 other universe symbols to "
                "average a pairwise correlation across"
            )
        if not 0.0 < corr_threshold < 1.0:
            raise ValueError("corr_threshold must be in (0, 1)")
        self.name = name
        self.params: dict[str, object] = {
            "corr_lookback": corr_lookback, "corr_threshold": corr_threshold,
            "trend_lookback": trend_lookback,
        }
        self._symbol = symbol
        self._universe = list(universe)
        self._corr_lookback = corr_lookback
        self._corr_threshold = corr_threshold
        self._trend_lookback = trend_lookback
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
                    reason=f"{self.name}: idiosyncratic regime, own-symbol uptrend",
                )
            ]
        self._position = "FLAT"
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction="FLAT", strength=0.0,
                intent_kind="EXIT", bar_ts=ev.ts_open,
                reason=f"{self.name}: systemic regime or trend faded",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None

    def _target_state(self) -> Literal["LONG", "FLAT"] | None:
        needed = self._corr_lookback + 1
        if any(len(self._history[sym]) < needed for sym in self._universe):
            return None  # not enough history for the whole universe yet
        if len(self._history[self._symbol]) < self._trend_lookback + 1:
            return None
        if self._avg_pairwise_correlation() >= self._corr_threshold:
            return "FLAT"  # systemic regime -- stay out regardless of trend
        own = self._history[self._symbol]
        uptrend = own[-1] > own[-self._trend_lookback - 1]
        return "LONG" if uptrend else "FLAT"

    def _avg_pairwise_correlation(self) -> float:
        # Every symbol's window is sliced from the SAME common length, not
        # each symbol's own "last N" -- within one universe cycle, the
        # adapter's own symbol is decided before siblings later in the same
        # cycle have appended their bar, so its own history can be
        # transiently one bar ahead of theirs. Anchoring every window to
        # `min(len(...))` keeps the compared windows time-aligned instead of
        # silently comparing each symbol's own most-recent-but-offset slice.
        common_len = min(len(self._history[sym]) for sym in self._universe)
        start = common_len - (self._corr_lookback + 1)
        windows = {
            sym: _returns(self._history[sym][start:common_len]) for sym in self._universe
        }
        correlations = [
            _pearson(windows[a], windows[b])
            for i, a in enumerate(self._universe)
            for b in self._universe[i + 1 :]
        ]
        return sum(correlations) / len(correlations)
