"""docs/14 sleeve F (v4): `BasisCarryAdapter` must observe the perp
instrument's price as a foreign symbol (reusing the multi-symbol
`Context`/`Session` extension from sleeve C/D) and act only on its own
symbol's bar, computing a real spot-vs-perp basis.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.adapters.basis_carry_adapter import BasisCarryAdapter

START = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: Symbol, i: int, price: float) -> MarketEvent:
    p = Decimal(str(price))
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=START + timedelta(minutes=i),
        o=p, h=p + Decimal("1"), l=p - Decimal("1"), c=p, v=100.0, source_version="test",
    )


def test_rejects_perp_symbol_equal_to_symbol() -> None:
    with pytest.raises(ValueError, match="perp_symbol"):
        BasisCarryAdapter(symbol="BTC-USDT", name="x", perp_symbol="BTC-USDT")


def test_no_signal_until_the_perp_leg_has_at_least_one_bar() -> None:
    adapter = BasisCarryAdapter(symbol="BTC-USDT", name="x", perp_symbol="BTC-USDT-PERP")
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(3):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0), ctx))
    assert signals == []


def test_goes_long_when_perp_trades_at_a_rich_premium_to_spot() -> None:
    adapter = BasisCarryAdapter(
        symbol="BTC-USDT", name="x", perp_symbol="BTC-USDT-PERP",
        entry_basis=0.005, exit_basis=0.0,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(5):
        # perp trades ~1% above spot -- a rich premium.
        signals.extend(adapter.on_market(_bar("BTC-USDT-PERP", i, 101.0), ctx))
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"
    assert enters[0].symbol == "BTC-USDT"


def test_stays_flat_when_the_basis_is_narrow() -> None:
    adapter = BasisCarryAdapter(
        symbol="BTC-USDT", name="x", perp_symbol="BTC-USDT-PERP",
        entry_basis=0.01, exit_basis=0.0,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(5):
        signals.extend(adapter.on_market(_bar("BTC-USDT-PERP", i, 100.05), ctx))
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0), ctx))
    assert [s for s in signals if s.intent_kind == "ENTER"] == []


def test_a_foreign_bar_never_signals_for_its_own_symbol() -> None:
    adapter = BasisCarryAdapter(symbol="BTC-USDT", name="x", perp_symbol="BTC-USDT-PERP")
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    assert adapter.on_market(_bar("BTC-USDT-PERP", 0, 101.0), ctx) == []


def test_a_bar_outside_the_pair_is_ignored() -> None:
    adapter = BasisCarryAdapter(symbol="BTC-USDT", name="x", perp_symbol="BTC-USDT-PERP")
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    assert adapter.on_market(_bar("ETH-USDT", 0, 10.0), ctx) == []


def test_on_fill_is_a_no_op() -> None:
    adapter = BasisCarryAdapter(symbol="BTC-USDT", name="x", perp_symbol="BTC-USDT-PERP")
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise
