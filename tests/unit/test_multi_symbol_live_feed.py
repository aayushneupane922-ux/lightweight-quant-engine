"""`MultiSymbolLiveFeed` (V5 M27 Universe Core): merges each symbol's own
`LiveFeed` poll into one `ts_open`-sorted stream; a symbol returning
nothing this poll just contributes nothing, never a crash.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe
from lqe.data.base import DataCapabilities
from lqe.live.multi_symbol_feed import MultiSymbolLiveFeed

BTC: Symbol = "BTC-USDT"
ETH: Symbol = "ETH-USDT"
TF: Timeframe = "1m"


def _bar(symbol: Symbol, ts_open: datetime, close: float) -> MarketEvent:
    return MarketEvent(
        exchange="fake", symbol=symbol, timeframe=TF, ts_open=ts_open,
        o=Decimal(str(close)), h=Decimal(str(close + 1)), l=Decimal(str(close - 1)),
        c=Decimal(str(close)), v=1.0, source_version="fake:1",
    )


class _PerSymbolFakeAdapter:
    """Serves a different, independently-mutable bar sequence per symbol."""

    def __init__(self, bars_by_symbol: dict[Symbol, list[MarketEvent]]) -> None:
        self.bars_by_symbol = bars_by_symbol

    def capabilities(self) -> DataCapabilities:
        return DataCapabilities(bars=True)

    def stream(
        self, symbols: list[Symbol], tf: Timeframe,
        start: datetime | None = None, end: datetime | None = None,
    ) -> Iterator[MarketEvent]:
        for sym in symbols:
            for bar in self.bars_by_symbol.get(sym, []):
                if start is not None and bar.ts_open < start:
                    continue
                if end is not None and bar.ts_open >= end:
                    continue
                yield bar


def _sequence(symbol: Symbol, n: int, *, now: datetime) -> list[MarketEvent]:
    return [_bar(symbol, now - timedelta(minutes=n - 1 - i), 100.0 + i) for i in range(n)]


def test_seed_history_merges_and_sorts_across_symbols() -> None:
    now = datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)
    adapter = _PerSymbolFakeAdapter(
        {BTC: _sequence(BTC, 10, now=now), ETH: _sequence(ETH, 10, now=now)}
    )
    feed = MultiSymbolLiveFeed.build(
        adapter=adapter, symbols=[BTC, ETH], timeframe=TF, now_fn=lambda: now
    )
    history = feed.seed_history(lookback_bars=5)
    assert len(history) == 10  # 5 per symbol
    assert [b.ts_open for b in history] == sorted(b.ts_open for b in history)
    assert {b.symbol for b in history} == {BTC, ETH}


def test_poll_new_bars_merges_new_bars_across_symbols() -> None:
    clock = {"now": datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)}
    adapter = _PerSymbolFakeAdapter(
        {BTC: _sequence(BTC, 10, now=clock["now"]), ETH: _sequence(ETH, 10, now=clock["now"])}
    )
    feed = MultiSymbolLiveFeed.build(
        adapter=adapter, symbols=[BTC, ETH], timeframe=TF, poll_seconds=30.0,
        now_fn=lambda: clock["now"],
    )
    feed.seed_history(lookback_bars=5)
    assert feed.poll_new_bars() == []

    clock["now"] += timedelta(minutes=2)
    adapter.bars_by_symbol[BTC] = _sequence(BTC, 12, now=clock["now"])
    adapter.bars_by_symbol[ETH] = _sequence(ETH, 12, now=clock["now"])
    new_bars = feed.poll_new_bars()
    assert len(new_bars) == 4  # 2 new closed bars per symbol
    assert [b.ts_open for b in new_bars] == sorted(b.ts_open for b in new_bars)


def test_a_symbol_with_no_new_bars_contributes_nothing_not_a_crash() -> None:
    clock = {"now": datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)}
    # ETH's exchange genuinely has nothing beyond a handful of already-
    # closed bars -- no matter how much time passes, it never has anything
    # new (its last bar is fully seeded, just outside the seed lookback).
    eth_bars = _sequence(ETH, 5, now=clock["now"] - timedelta(minutes=1))
    adapter = _PerSymbolFakeAdapter({BTC: _sequence(BTC, 10, now=clock["now"]), ETH: eth_bars})
    feed = MultiSymbolLiveFeed.build(
        adapter=adapter, symbols=[BTC, ETH], timeframe=TF, now_fn=lambda: clock["now"]
    )
    feed.seed_history(lookback_bars=5)

    clock["now"] += timedelta(minutes=2)
    adapter.bars_by_symbol[BTC] = _sequence(BTC, 12, now=clock["now"])
    # ETH's adapter is untouched -- genuinely no new data this cycle.
    new_bars = feed.poll_new_bars()
    assert new_bars
    assert all(b.symbol == BTC for b in new_bars)


def test_resume_from_positions_each_symbols_cursor_independently() -> None:
    now = datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)
    btc_bars = _sequence(BTC, 10, now=now)
    eth_bars = _sequence(ETH, 10, now=now)
    adapter = _PerSymbolFakeAdapter({BTC: btc_bars, ETH: eth_bars})
    feed = MultiSymbolLiveFeed.build(
        adapter=adapter, symbols=[BTC, ETH], timeframe=TF, now_fn=lambda: now
    )
    feed.resume_from({BTC: btc_bars[:9], ETH: eth_bars[:8]})
    caught_up = feed.poll_new_bars()
    # BTC has nothing left to catch up (resumed at the newest closed bar);
    # ETH is missing its newest closed bar (index 8) and must catch it up.
    assert [b.symbol for b in caught_up] == [ETH]
    assert caught_up[0].c == Decimal("108")
