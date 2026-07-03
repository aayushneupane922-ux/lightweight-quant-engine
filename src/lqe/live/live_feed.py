"""Real-time market data polling (post-v1.0 extension, user-requested — see
HANDOFF.md). Wraps the existing `CcxtMarketDataAdapter` (public OHLCV
endpoints only, no order capability — docs/06 §6.3) to repeatedly fetch the
newest bars and yield only genuinely new, fully-closed ones.

This module never calls anything beyond `MarketDataAdapter.stream()` — it
inherits the "no trading method" guarantee `tests/safety/
test_no_order_capable_data_adapter.py` already enforces on the adapter it
wraps; there is nothing here for that scan to miss.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe
from lqe.data.base import MarketDataAdapter

_TF_SECONDS: dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900,
    "1h": 3600, "4h": 14400, "1d": 86400,
}


def timeframe_seconds(tf: Timeframe) -> int:
    try:
        return _TF_SECONDS[tf]
    except KeyError:
        raise ValueError(f"unsupported timeframe for live polling: {tf!r}") from None


@dataclass
class LiveFeed:
    """Polls `adapter` for `symbol`/`timeframe` bars. Stateful only in the
    sense of remembering the last bar's `ts_open` it has already yielded, so
    repeated polls never re-yield or duplicate a bar."""

    adapter: MarketDataAdapter
    symbol: Symbol
    timeframe: Timeframe
    poll_seconds: float = 60.0
    # Injectable so "is this bar still forming" is testable deterministically
    # (a fixed fake `now`) rather than tied to the real wall clock; defaults
    # to real time for actual live polling.
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731
    _last_ts_open: datetime | None = None

    def seed_history(self, *, lookback_bars: int) -> list[MarketEvent]:
        """One fetch of recent closed bars for indicator warm-up. Advances
        the internal dedup cursor so `poll_new_bars` never re-yields these."""
        since = self.now_fn() - timedelta(
            seconds=timeframe_seconds(self.timeframe) * (lookback_bars + 2)
        )
        bars = self._closed_bars(since=since)
        bars = bars[-lookback_bars:] if len(bars) > lookback_bars else bars
        if bars:
            self._last_ts_open = bars[-1].ts_open
        return bars

    def resume_from(self, bars: list[MarketEvent]) -> None:
        """Position the dedup cursor at the end of an externally-supplied bar
        history (docs/12 M15: e.g. reconstructed from a persisted audit log
        on restart) instead of a fresh `seed_history()` fetch -- so the next
        `poll_new_bars()` only returns genuinely new bars beyond it."""
        if bars:
            self._last_ts_open = bars[-1].ts_open

    def poll_new_bars(self) -> list[MarketEvent]:
        """One fetch; returns only bars strictly newer than the last one
        already returned (by this feed instance), ascending, all fully
        closed (the still-forming bar is always excluded)."""
        since = self._last_ts_open
        bars = self._closed_bars(since=since)
        new = [b for b in bars if self._last_ts_open is None or b.ts_open > self._last_ts_open]
        if new:
            self._last_ts_open = new[-1].ts_open
        return new

    def _closed_bars(self, *, since: datetime | None) -> list[MarketEvent]:
        now = self.now_fn()
        tf_s = timeframe_seconds(self.timeframe)
        bars = list(self.adapter.stream([self.symbol], self.timeframe, start=since))
        # A bar is only "closed" once a full timeframe has elapsed since it
        # opened -- otherwise it's still forming and would look like a
        # partial/incomplete candle to every strategy fed it.
        return [b for b in bars if (now - b.ts_open).total_seconds() >= tf_s]

    def run_forever(
        self,
        on_bars: Callable[[list[MarketEvent]], None],
        *,
        should_stop: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Blocking loop: poll, hand any new bars to `on_bars`, sleep, repeat.
        `should_stop` is checked between polls so a caller can shut this down
        from another thread (e.g. on KILL) without killing the process."""
        while should_stop is None or not should_stop():
            new_bars = self.poll_new_bars()
            if new_bars:
                on_bars(new_bars)
            sleep(self.poll_seconds)


def dedupe_sorted(bars: Iterable[MarketEvent]) -> list[MarketEvent]:
    """Defensive helper: sort by ts_open and drop exact-timestamp repeats,
    keeping the first occurrence. Exchanges occasionally return an overlap
    bar at a poll boundary; this makes that harmless."""
    seen: set[datetime] = set()
    out: list[MarketEvent] = []
    for bar in sorted(bars, key=lambda b: b.ts_open):
        if bar.ts_open in seen:
            continue
        seen.add(bar.ts_open)
        out.append(bar)
    return out
