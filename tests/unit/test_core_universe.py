"""`core.universe.Universe` (V5 M27): groups a multi-symbol bar stream
into synchronized per-timestamp cycles; a symbol missing a cycle is
reported, not a crash. Distinct from `portfolio/universe.py`'s unrelated
`RankedUniverse` (factor-based survivorship/instrument-selection helper,
see test_universe.py) -- this one synchronizes a live/backtest bar stream.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.core.universe import Universe

BTC: Symbol = "BTC-USDT"
ETH: Symbol = "ETH-USDT"
SOL: Symbol = "SOL-USDT"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: Symbol, minute: int, price: str = "100") -> MarketEvent:
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=NOW + timedelta(minutes=minute),
        o=Decimal(price), h=Decimal(price), l=Decimal(price), c=Decimal(price),
        v=1.0, source_version="test",
    )


def test_cycles_group_bars_sharing_a_timestamp() -> None:
    bars = [_bar(BTC, 0), _bar(ETH, 0), _bar(SOL, 0), _bar(BTC, 1), _bar(ETH, 1), _bar(SOL, 1)]
    universe = Universe([BTC, ETH, SOL])
    cycles = list(universe.cycles(bars))
    assert len(cycles) == 2
    assert [b.symbol for b in cycles[0].bars] == [BTC, ETH, SOL]  # sorted
    assert cycles[0].missing == ()
    assert cycles[1].missing == ()


def test_a_missing_symbol_is_reported_not_crashed() -> None:
    # SOL never shows up at minute 0; the other two still form a cycle.
    bars = [_bar(BTC, 0), _bar(ETH, 0), _bar(BTC, 1), _bar(ETH, 1), _bar(SOL, 1)]
    universe = Universe([BTC, ETH, SOL])
    cycles = list(universe.cycles(bars))
    assert len(cycles) == 2
    assert cycles[0].missing == (SOL,)
    assert [b.symbol for b in cycles[0].bars] == [BTC, ETH]
    assert cycles[1].missing == ()


def test_last_seen_tracks_the_most_recent_bar_per_symbol() -> None:
    bars = [_bar(BTC, 0), _bar(ETH, 0), _bar(BTC, 1)]
    universe = Universe([BTC, ETH])
    list(universe.cycles(bars))
    assert universe.last_seen[BTC] == NOW + timedelta(minutes=1)
    assert universe.last_seen[ETH] == NOW + timedelta(minutes=0)


def test_bar_for_a_symbol_outside_the_universe_raises() -> None:
    universe = Universe([BTC])
    with pytest.raises(ValueError, match="outside this Universe"):
        list(universe.cycles([_bar(ETH, 0)]))


def test_out_of_order_bars_raise_rather_than_silently_desync() -> None:
    universe = Universe([BTC])
    bars = [_bar(BTC, 1), _bar(BTC, 0)]  # minute 0 arrives after minute 1
    with pytest.raises(ValueError, match="not time-ordered"):
        list(universe.cycles(bars))


def test_cycling_the_same_stream_twice_is_deterministic() -> None:
    bars = [_bar(BTC, 0), _bar(ETH, 0), _bar(BTC, 1), _bar(SOL, 1)]
    cycles_a = list(Universe([BTC, ETH, SOL]).cycles(bars))
    cycles_b = list(Universe([BTC, ETH, SOL]).cycles(bars))
    assert cycles_a == cycles_b


def test_requires_at_least_one_symbol() -> None:
    with pytest.raises(ValueError, match="at least one symbol"):
        Universe([])
