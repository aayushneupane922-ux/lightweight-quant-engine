"""`CrossExchangeFundingAdapter` (docs/14 sleeve F, v4): cross-exchange
funding-rate differential -- the same instrument's funding rate can differ
meaningfully across venues (docs/14's own F row lists this explicitly,
distinct from sleeve K's cross-exchange *price* spread/triangular arb,
which is research/paper-only and latency-sensitive).

Takes two fixed `funding_history` side-channels (one per venue), the same
forward-fill-no-look-ahead lookup as `funding_carry_adapter.py`. No new
engine capability needed -- this is driven purely by the two supplied
series, not by observing foreign bars.

**Honesty note** (same as the other sleeve F adapters): trades only the
spot leg on `symbol`, gated by which venue's funding is more favorable.
Does not itself arbitrage the two venues (that would need real positions
on both exchanges, out of scope for this single-book paper engine) --
declared in the manifest's `failure_modes`.
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
    def __init__(self, funding_history: Sequence[tuple[datetime, float]]) -> None:
        ordered = sorted(funding_history, key=lambda pair: pair[0])
        self._timestamps = [ts for ts, _ in ordered]
        self._rates = [rate for _, rate in ordered]

    def as_of(self, ts: datetime) -> float | None:
        idx = bisect.bisect_right(self._timestamps, ts) - 1
        return self._rates[idx] if idx >= 0 else None


class CrossExchangeFundingAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        funding_history_a: Sequence[tuple[datetime, float]],
        funding_history_b: Sequence[tuple[datetime, float]],
        entry_diff: float = 0.0001,
        exit_diff: float = 0.0,
    ) -> None:
        self.name = name
        self.params: dict[str, object] = {"entry_diff": entry_diff, "exit_diff": exit_diff}
        self._symbol = symbol
        self._funding_a = _FundingLookup(funding_history_a)
        self._funding_b = _FundingLookup(funding_history_b)
        self._entry_diff = entry_diff
        self._exit_diff = exit_diff
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        rate_a = self._funding_a.as_of(ev.ts_open)
        rate_b = self._funding_b.as_of(ev.ts_open)
        if rate_a is None or rate_b is None:
            return []
        diff = rate_a - rate_b

        target: Literal["LONG", "FLAT"] | None = None
        if diff >= self._entry_diff:
            target = "LONG"
        elif diff <= self._exit_diff:
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
                reason=f"{self.name}: cross-exchange funding diff={diff:.5f}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
