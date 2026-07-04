"""`FundingCarryAdapter` + `FundingMomentumAdapter` (docs/14 sleeve F, v4):
funding-rate-driven strategies on a single (spot) instrument.

**Important honesty note** (non-negotiable #9, no profitability claims):
the textbook "perp funding-rate carry" trade is long spot / short perp,
collecting the funding differential market-neutrally. This engine's
short-selling path is explicitly out of scope (`portfolio/accounting.py`
raises rather than silently going short; `risk/rules.py` rejects any SELL
that would take a position net-short) -- the same boundary that made
sleeve C/D's cross-sectional/stat-arb strategies long-only. So these
adapters are honestly a **directional bet on the spot instrument's own
price, gated by a funding-rate signal historically associated with carry
opportunity** -- NOT a market-neutral carry harvest. They do not collect
funding payments; their P&L is ordinary spot price movement. Declared in
each manifest's `failure_modes`, not silently overclaimed.

Both classes take a fixed `funding_history: Sequence[tuple[datetime,
float]]` side-channel (real ccxt-fetched or ingested data, supplied at
construction) -- the same "known series, looked up per bar" pattern
`StatsmodelsPairsAdapter` already uses for `hedge_closes`. Forward-filled,
no look-ahead: only observations with `ts <= bar.ts_open` are ever used.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


class _FundingLookup:
    """Sorted (ts, rate) lookup with forward-fill, no look-ahead."""

    def __init__(self, funding_history: Sequence[tuple[datetime, float]]) -> None:
        ordered = sorted(funding_history, key=lambda pair: pair[0])
        self._timestamps = [ts for ts, _ in ordered]
        self._rates = [rate for _, rate in ordered]

    def as_of(self, ts: datetime) -> float | None:
        idx = bisect.bisect_right(self._timestamps, ts) - 1
        return self._rates[idx] if idx >= 0 else None

    def window_as_of(self, ts: datetime, lookback: int) -> list[float] | None:
        idx = bisect.bisect_right(self._timestamps, ts) - 1
        if idx < lookback:
            return None
        return self._rates[idx - lookback + 1 : idx + 1]


class FundingCarryAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        funding_history: Sequence[tuple[datetime, float]],
        entry_rate: float = 0.0001,
        exit_rate: float = 0.0,
    ) -> None:
        self.name = name
        self.params: dict[str, object] = {"entry_rate": entry_rate, "exit_rate": exit_rate}
        self._symbol = symbol
        self._funding = _FundingLookup(funding_history)
        self._entry_rate = entry_rate
        self._exit_rate = exit_rate
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        rate = self._funding.as_of(ev.ts_open)
        if rate is None:
            return []

        target: Literal["LONG", "FLAT"] | None = None
        if rate >= self._entry_rate:
            target = "LONG"
        elif rate <= self._exit_rate:
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
                reason=f"{self.name}: funding rate={rate:.5f}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None


class FundingMomentumAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        funding_history: Sequence[tuple[datetime, float]],
        mode: Literal["momentum", "reversion"] = "momentum",
        lookback: int = 3,
        entry_threshold: float = 0.00005,
        exit_threshold: float = 0.0,
    ) -> None:
        self.name = name
        self.params: dict[str, object] = {
            "mode": mode, "lookback": lookback,
            "entry_threshold": entry_threshold, "exit_threshold": exit_threshold,
        }
        self._symbol = symbol
        self._funding = _FundingLookup(funding_history)
        self._mode = mode
        self._lookback = lookback
        self._entry_threshold = entry_threshold
        self._exit_threshold = exit_threshold
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        signal_value = self._signal_value(ev.ts_open)
        if signal_value is None:
            return []

        target: Literal["LONG", "FLAT"] | None = None
        if signal_value >= self._entry_threshold:
            target = "LONG"
        elif signal_value <= self._exit_threshold:
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
                reason=f"{self.name}: funding {self._mode} signal={signal_value:.5f}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None

    def _signal_value(self, ts: datetime) -> float | None:
        window = self._funding.window_as_of(ts, self._lookback)
        if window is None:
            return None
        if self._mode == "momentum":
            # rate-of-change over the window: rising funding -> bullish crowd
            # building, ride the trend.
            return window[-1] - window[0]
        # reversion: how far the current rate sits below its own recent
        # rolling average -- a deep negative outlier (crowd extremely
        # short) bets on a bounce, the mirror image of chasing momentum.
        mean = sum(window) / len(window)
        return mean - window[-1]
