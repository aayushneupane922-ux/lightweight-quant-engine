"""docs/14 sleeve D (v4): stat-arb beyond simple OLS-hedge pairs.
`DistancePairsAdapter`, `LeadLagAdapter`, `BasketArbAdapter` must each act
only on genuine relative-value/spillover signals across a multi-symbol
history, not on their own price path in isolation -- the same discipline
`CrossSectionalAdapter` (sleeve C) is held to.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.adapters.stat_arb_adapter import (
    BasketArbAdapter,
    DistancePairsAdapter,
    LeadLagAdapter,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: Symbol, i: int, price: float) -> MarketEvent:
    p = Decimal(str(price))
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=START + timedelta(minutes=i),
        o=p, h=p + Decimal("1"), l=p - Decimal("1"), c=p, v=100.0, source_version="test",
    )


# --- DistancePairsAdapter ---------------------------------------------


def test_distance_pairs_rejects_partner_equal_to_symbol() -> None:
    with pytest.raises(ValueError, match="partner"):
        DistancePairsAdapter(symbol="BTC-USDT", name="x", partner="BTC-USDT")


def test_distance_pairs_no_signal_until_window_is_full() -> None:
    adapter = DistancePairsAdapter(symbol="BTC-USDT", name="x", partner="ETH-USDT", window=5)
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(3):
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, 10.0), ctx))
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0), ctx))
    assert signals == []


def test_distance_pairs_goes_long_when_it_drifts_cheap_vs_its_partner() -> None:
    adapter = DistancePairsAdapter(
        symbol="BTC-USDT", name="x", partner="ETH-USDT", window=5, entry_z=1.5, exit_z=0.3,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    btc = [100, 100, 100, 100, 80]
    eth = [10, 10, 10, 10, 10]
    for i in range(5):
        # partner's bar for this timestamp must land first, or the
        # own-symbol check fires one bar too early against stale history.
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, eth[i]), ctx))
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, btc[i]), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"
    assert enters[0].symbol == "BTC-USDT"


def test_distance_pairs_a_foreign_bar_never_signals_for_its_own_symbol() -> None:
    adapter = DistancePairsAdapter(symbol="BTC-USDT", name="x", partner="ETH-USDT", window=2)
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    result = adapter.on_market(_bar("ETH-USDT", 0, 10.0), ctx)
    assert result == []


def test_distance_pairs_a_bar_outside_the_pair_is_ignored() -> None:
    adapter = DistancePairsAdapter(symbol="BTC-USDT", name="x", partner="ETH-USDT", window=2)
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    result = adapter.on_market(_bar("DOGE-USDT", 0, 1.0), ctx)
    assert result == []


def test_distance_pairs_on_fill_is_a_no_op() -> None:
    adapter = DistancePairsAdapter(symbol="BTC-USDT", name="x", partner="ETH-USDT")
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise


# --- LeadLagAdapter ------------------------------------------------------


def test_lead_lag_rejects_leader_equal_to_symbol() -> None:
    with pytest.raises(ValueError, match="leader"):
        LeadLagAdapter(symbol="ETH-USDT", name="x", leader="ETH-USDT")


def test_lead_lag_no_signal_until_lookback_is_full() -> None:
    adapter = LeadLagAdapter(symbol="ETH-USDT", name="x", leader="BTC-USDT", lookback=3)
    ctx = Context(symbol="ETH-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(2):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0 + i * 10), ctx))
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, 10.0), ctx))
    assert signals == []


def test_lead_lag_goes_long_when_the_leader_rallies_hard() -> None:
    adapter = LeadLagAdapter(
        symbol="ETH-USDT", name="x", leader="BTC-USDT", lookback=3,
        entry_return=0.02, exit_return=0.0,
    )
    ctx = Context(symbol="ETH-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    btc = [100, 101, 102, 110]
    eth = [10, 10, 10, 10]
    for i in range(4):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, btc[i]), ctx))
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, eth[i]), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"
    assert enters[0].symbol == "ETH-USDT"


def test_lead_lag_returns_to_flat_once_the_leaders_momentum_fades() -> None:
    adapter = LeadLagAdapter(
        symbol="ETH-USDT", name="x", leader="BTC-USDT", lookback=2,
        entry_return=0.02, exit_return=0.0,
    )
    ctx = Context(symbol="ETH-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    # BTC rallies (triggers LONG), then goes flat/negative (triggers FLAT).
    btc = [100, 100, 110, 110, 108]
    for i, price in enumerate(btc):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, price), ctx))
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, 10.0), ctx))
    exits = [s for s in signals if s.intent_kind == "EXIT"]
    assert len(exits) == 1
    assert exits[0].direction == "FLAT"


def test_lead_lag_a_bar_outside_the_pair_is_ignored() -> None:
    adapter = LeadLagAdapter(symbol="ETH-USDT", name="x", leader="BTC-USDT", lookback=2)
    ctx = Context(symbol="ETH-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    result = adapter.on_market(_bar("DOGE-USDT", 0, 1.0), ctx)
    assert result == []


def test_lead_lag_on_fill_is_a_no_op() -> None:
    adapter = LeadLagAdapter(symbol="ETH-USDT", name="x", leader="BTC-USDT")
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise


# --- BasketArbAdapter ------------------------------------------------------


def test_basket_arb_rejects_symbol_inside_its_own_basket() -> None:
    with pytest.raises(ValueError, match="own reference basket"):
        BasketArbAdapter(symbol="BTC-USDT", name="x", basket=("BTC-USDT", "ETH-USDT"))


def test_basket_arb_rejects_an_empty_basket() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        BasketArbAdapter(symbol="BTC-USDT", name="x", basket=())


def test_basket_arb_no_signal_until_window_is_full() -> None:
    adapter = BasketArbAdapter(
        symbol="BTC-USDT", name="x", basket=("ETH-USDT", "SOL-USDT"), window=5,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(3):
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, 10.0), ctx))
        signals.extend(adapter.on_market(_bar("SOL-USDT", i, 20.0), ctx))
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0), ctx))
    assert signals == []


def test_basket_arb_goes_long_when_it_drifts_cheap_vs_the_basket() -> None:
    adapter = BasketArbAdapter(
        symbol="BTC-USDT", name="x", basket=("ETH-USDT", "SOL-USDT"),
        window=5, entry_z=1.5, exit_z=0.3,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    btc = [100, 100, 100, 100, 80]
    eth = [10, 10, 10, 10, 10]
    sol = [20, 20, 20, 20, 20]
    for i in range(5):
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, eth[i]), ctx))
        signals.extend(adapter.on_market(_bar("SOL-USDT", i, sol[i]), ctx))
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, btc[i]), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"
    assert enters[0].symbol == "BTC-USDT"


def test_basket_arb_a_bar_outside_the_basket_is_ignored() -> None:
    adapter = BasketArbAdapter(symbol="BTC-USDT", name="x", basket=("ETH-USDT", "SOL-USDT"))
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    result = adapter.on_market(_bar("DOGE-USDT", 0, 1.0), ctx)
    assert result == []


def test_basket_arb_on_fill_is_a_no_op() -> None:
    adapter = BasketArbAdapter(symbol="BTC-USDT", name="x", basket=("ETH-USDT", "SOL-USDT"))
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise
