"""`MultiSymbolLiveFeed` (V5 M27 "Universe Core", docs/15): the live-side
counterpart to `CcxtMarketDataAdapter.stream()`'s now-interleaved
multi-symbol fetch. Wraps one `LiveFeed` per symbol (each keeps its own
independent dedup cursor, exactly as today) and merges every poll's new
bars into one `ts_open`-sorted stream -- the same contract
`core.universe.Universe.cycles()` expects.

A symbol returning 0 new bars this poll simply contributes nothing to the
merged stream; `Universe.cycles()` downstream reports it as missing that
cycle (docs/15: "late/missing symbol -> no-trade + logged", never a crash
or desync for the other symbols).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe
from lqe.data.base import MarketDataAdapter
from lqe.live.live_feed import LiveFeed


@dataclass
class MultiSymbolLiveFeed:
    feeds: dict[Symbol, LiveFeed]

    @classmethod
    def build(
        cls,
        *,
        adapter: MarketDataAdapter,
        symbols: list[Symbol],
        timeframe: Timeframe,
        poll_seconds: float = 60.0,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),  # noqa: E731
    ) -> MultiSymbolLiveFeed:
        return cls(
            feeds={
                sym: LiveFeed(
                    adapter=adapter, symbol=sym, timeframe=timeframe,
                    poll_seconds=poll_seconds, now_fn=now_fn,
                )
                for sym in symbols
            }
        )

    @property
    def symbols(self) -> list[Symbol]:
        return list(self.feeds)

    def seed_history(self, *, lookback_bars: int) -> list[MarketEvent]:
        """One seed fetch per symbol, merged and `ts_open`-sorted."""
        bars = [
            bar for feed in self.feeds.values() for bar in feed.seed_history(
                lookback_bars=lookback_bars
            )
        ]
        bars.sort(key=lambda b: b.ts_open)
        return bars

    def resume_from(self, bars_by_symbol: Mapping[Symbol, list[MarketEvent]]) -> None:
        """Position each symbol's dedup cursor from an externally-supplied
        per-symbol bar history (docs/12 M15's resume pattern, extended to
        a universe: e.g. reconstructed from a persisted multi-symbol audit
        log on restart)."""
        for sym, feed in self.feeds.items():
            feed.resume_from(bars_by_symbol.get(sym, []))

    def poll_new_bars(self) -> list[MarketEvent]:
        """One poll per symbol; merges every symbol's genuinely-new,
        fully-closed bars into one `ts_open`-sorted stream."""
        bars = [bar for feed in self.feeds.values() for bar in feed.poll_new_bars()]
        bars.sort(key=lambda b: b.ts_open)
        return bars
