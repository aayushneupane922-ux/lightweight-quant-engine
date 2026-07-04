"""docs/14 sleeve F (v4): `FundingCarryAdapter`/`FundingMomentumAdapter`
must act only on genuine funding-rate signals looked up from a fixed,
forward-filled series -- never look ahead past the current bar's own
timestamp, and never trade before any funding observation exists yet.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.adapters.funding_carry_adapter import (
    FundingCarryAdapter,
    FundingMomentumAdapter,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: Symbol, i: int, price: float = 100.0) -> MarketEvent:
    p = Decimal(str(price))
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=START + timedelta(minutes=i),
        o=p, h=p + Decimal("1"), l=p - Decimal("1"), c=p, v=100.0, source_version="test",
    )


# --- FundingCarryAdapter -------------------------------------------------


def test_carry_no_signal_before_any_funding_observation() -> None:
    adapter = FundingCarryAdapter(
        symbol="BTC-USDT", name="x",
        funding_history=[(START + timedelta(minutes=5), 0.0003)],
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(5):  # bars strictly before the only funding observation
        signals.extend(adapter.on_market(_bar("BTC-USDT", i), ctx))
    assert signals == []


def test_carry_goes_long_once_the_forward_filled_rate_clears_entry() -> None:
    adapter = FundingCarryAdapter(
        symbol="BTC-USDT", name="x",
        funding_history=[(START, 0.0001), (START + timedelta(minutes=5), 0.0003)],
        entry_rate=0.0002, exit_rate=0.0,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(10):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"


def test_carry_never_looks_ahead_past_its_own_bar() -> None:
    # a favorable rate exists, but only *after* every bar processed here --
    # forward-fill must never use a future observation.
    adapter = FundingCarryAdapter(
        symbol="BTC-USDT", name="x",
        funding_history=[(START + timedelta(minutes=100), 0.01)],
        entry_rate=0.0002,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(5):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i), ctx))
    assert signals == []


def test_carry_a_foreign_bar_is_ignored() -> None:
    adapter = FundingCarryAdapter(
        symbol="BTC-USDT", name="x", funding_history=[(START, 0.0003)], entry_rate=0.0002,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    assert adapter.on_market(_bar("ETH-USDT", 0), ctx) == []


def test_carry_on_fill_is_a_no_op() -> None:
    adapter = FundingCarryAdapter(symbol="BTC-USDT", name="x", funding_history=[])
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise


# --- FundingMomentumAdapter -----------------------------------------------


def test_momentum_no_signal_until_the_lookback_window_is_full() -> None:
    history = [(START + timedelta(minutes=i), 0.0001 * i) for i in range(3)]
    adapter = FundingMomentumAdapter(
        symbol="BTC-USDT", name="x", funding_history=history, mode="momentum", lookback=3,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(3):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i), ctx))
    assert signals == []


def test_momentum_goes_long_when_funding_is_rising() -> None:
    history = [(START + timedelta(minutes=i), 0.0001 * i) for i in range(10)]
    adapter = FundingMomentumAdapter(
        symbol="BTC-USDT", name="x", funding_history=history, mode="momentum",
        lookback=3, entry_threshold=0.0002, exit_threshold=0.0,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(10):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"


def test_reversion_goes_long_on_a_deep_negative_funding_dip_then_flattens() -> None:
    flat = 0.0001
    history = (
        [(START + timedelta(minutes=i), flat) for i in range(5)]
        + [(START + timedelta(minutes=5), -0.001)]
        + [(START + timedelta(minutes=i), flat) for i in range(6, 10)]
    )
    adapter = FundingMomentumAdapter(
        symbol="BTC-USDT", name="x", funding_history=history, mode="reversion",
        lookback=3, entry_threshold=0.0005, exit_threshold=0.0,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(10):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    exits = [s for s in signals if s.intent_kind == "EXIT"]
    assert len(enters) == 1 and enters[0].direction == "LONG"
    assert len(exits) == 1 and exits[0].direction == "FLAT"


def test_momentum_a_foreign_bar_is_ignored() -> None:
    adapter = FundingMomentumAdapter(symbol="BTC-USDT", name="x", funding_history=[])
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    assert adapter.on_market(_bar("ETH-USDT", 0), ctx) == []


def test_momentum_on_fill_is_a_no_op() -> None:
    adapter = FundingMomentumAdapter(symbol="BTC-USDT", name="x", funding_history=[])
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise
