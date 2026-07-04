"""docs/14 sleeve F (v4): `CrossExchangeFundingAdapter` must act only on a
genuine funding-rate differential between two supplied venue series --
distinct from `FundingCarryAdapter`'s single-venue level bet.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.adapters.cross_exchange_funding_adapter import CrossExchangeFundingAdapter

START = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: Symbol, i: int, price: float = 100.0) -> MarketEvent:
    p = Decimal(str(price))
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=START + timedelta(minutes=i),
        o=p, h=p + Decimal("1"), l=p - Decimal("1"), c=p, v=100.0, source_version="test",
    )


def test_no_signal_before_either_venue_has_an_observation() -> None:
    adapter = CrossExchangeFundingAdapter(
        symbol="BTC-USDT", name="x",
        funding_history_a=[(START + timedelta(minutes=5), 0.0005)],
        funding_history_b=[(START, 0.0001)],
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(5):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i), ctx))
    assert signals == []


def test_goes_long_when_venue_a_funding_is_favorably_higher() -> None:
    adapter = CrossExchangeFundingAdapter(
        symbol="BTC-USDT", name="x",
        funding_history_a=[(START, 0.0005)],
        funding_history_b=[(START, 0.0001)],
        entry_diff=0.0002, exit_diff=0.0,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = adapter.on_market(_bar("BTC-USDT", 0), ctx)
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"


def test_stays_flat_when_the_differential_is_narrow() -> None:
    adapter = CrossExchangeFundingAdapter(
        symbol="BTC-USDT", name="x",
        funding_history_a=[(START, 0.00011)],
        funding_history_b=[(START, 0.0001)],
        entry_diff=0.001, exit_diff=0.0,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = adapter.on_market(_bar("BTC-USDT", 0), ctx)
    assert [s for s in signals if s.intent_kind == "ENTER"] == []


def test_a_foreign_bar_is_ignored() -> None:
    adapter = CrossExchangeFundingAdapter(
        symbol="BTC-USDT", name="x", funding_history_a=[(START, 0.0005)],
        funding_history_b=[(START, 0.0001)], entry_diff=0.0002,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    assert adapter.on_market(_bar("ETH-USDT", 0), ctx) == []


def test_on_fill_is_a_no_op() -> None:
    adapter = CrossExchangeFundingAdapter(
        symbol="BTC-USDT", name="x", funding_history_a=[], funding_history_b=[],
    )
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise
