"""`LiveFeed` (post-v1.0 extension): dedups polled bars against a fake,
deterministic `MarketDataAdapter` -- no real network in a unit test.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe
from lqe.data.base import DataCapabilities
from lqe.live.live_feed import LiveFeed, dedupe_sorted, timeframe_seconds

SYMBOL: Symbol = "BTC-USDT"
TF: Timeframe = "1m"


def _bar(ts_open: datetime, close: float) -> MarketEvent:
    return MarketEvent(
        exchange="fake", symbol=SYMBOL, timeframe=TF, ts_open=ts_open,
        o=Decimal(str(close)), h=Decimal(str(close + 1)), l=Decimal(str(close - 1)),
        c=Decimal(str(close)), v=1.0, source_version="fake:1",
    )


class FakeAdapter:
    """A `MarketDataAdapter` serving a fixed, fully in-memory bar sequence
    ending at `now` -- so "closed" filtering in `LiveFeed` is exercised
    deterministically instead of depending on wall-clock timing."""

    def __init__(self, bars: list[MarketEvent]) -> None:
        self._bars = bars

    def capabilities(self) -> DataCapabilities:
        return DataCapabilities(bars=True)

    def stream(
        self, symbols: list[Symbol], tf: Timeframe,
        start: datetime | None = None, end: datetime | None = None,
    ) -> Iterator[MarketEvent]:
        for bar in self._bars:
            if start is not None and bar.ts_open < start:
                continue
            if end is not None and bar.ts_open >= end:
                continue
            yield bar


def _sequence(n: int, *, now: datetime) -> list[MarketEvent]:
    """`n` one-minute bars ending exactly at `now` (the last one still
    forming -- ts_open == now, not yet a full minute old)."""
    return [_bar(now - timedelta(minutes=n - 1 - i), 100.0 + i) for i in range(n)]


def test_seed_history_excludes_the_still_forming_bar() -> None:
    now = datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)  # mid-minute
    bars = _sequence(10, now=now)
    adapter = FakeAdapter(bars)
    feed = LiveFeed(adapter=adapter, symbol=SYMBOL, timeframe=TF, now_fn=lambda: now)

    history = feed.seed_history(lookback_bars=5)
    assert len(history) == 5
    # the very last bar in the fixture opens at `now` (< 60s old) -> excluded
    assert all((now - b.ts_open).total_seconds() >= 60 for b in history)


def test_poll_new_bars_returns_nothing_immediately_after_seeding() -> None:
    now = datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)
    adapter = FakeAdapter(_sequence(10, now=now))
    feed = LiveFeed(adapter=adapter, symbol=SYMBOL, timeframe=TF, now_fn=lambda: now)
    feed.seed_history(lookback_bars=5)
    assert feed.poll_new_bars() == []


def test_poll_new_bars_only_returns_strictly_newer_closed_bars() -> None:
    clock = {"now": datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)}
    adapter = FakeAdapter(_sequence(10, now=clock["now"]))
    feed = LiveFeed(
        adapter=adapter, symbol=SYMBOL, timeframe=TF, now_fn=lambda: clock["now"]
    )
    feed.seed_history(lookback_bars=5)

    # 2 minutes pass; 2 more bars have since closed (the very latest is still
    # forming and must stay excluded)
    clock["now"] = clock["now"] + timedelta(minutes=2)
    adapter._bars = _sequence(12, now=clock["now"])
    new_bars = feed.poll_new_bars()
    assert [b.c for b in new_bars] == [Decimal("109"), Decimal("110")]

    # polling again with no further advance yields nothing new
    assert feed.poll_new_bars() == []


def test_timeframe_seconds_rejects_unknown_timeframe() -> None:
    import pytest

    with pytest.raises(ValueError, match="unsupported timeframe"):
        timeframe_seconds("3m")  # type: ignore[arg-type]  # deliberately invalid input


def test_dedupe_sorted_drops_exact_timestamp_repeats() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [_bar(t0, 1.0), _bar(t0, 2.0), _bar(t0 + timedelta(minutes=1), 3.0)]
    out = dedupe_sorted(bars)
    assert [b.ts_open for b in out] == [t0, t0 + timedelta(minutes=1)]
    assert out[0].c == Decimal("1.0")  # first occurrence kept
