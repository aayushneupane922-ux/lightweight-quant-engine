"""Regression test for a real bug found while verifying v0.1 end-to-end:
`PaperBroker.mark_filled` was not shrinking a partially-filled order's
remaining qty, so a volume-capped order that took two bars to fill would
be re-filled from its *original* full qty on the second bar — double-
counting the fill.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.core.events import MarketEvent, Order
from lqe.execution.commission import BpsCommission
from lqe.execution.fills import MarketOrderFillSimulator
from lqe.execution.paper_broker import PaperBroker
from lqe.execution.slippage import FixedBpsSlippage

BASE_TS = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(offset_minutes: int, volume: float) -> MarketEvent:
    return MarketEvent(
        exchange="binance", symbol="BTC-USDT", timeframe="1m",
        ts_open=BASE_TS + timedelta(minutes=offset_minutes),
        o=Decimal("100"), h=Decimal("101"), l=Decimal("99"), c=Decimal("100"),
        v=volume, source_version="test",
    )


def test_partial_fill_shrinks_remaining_qty_not_double_counted() -> None:
    broker = PaperBroker()
    simulator = MarketOrderFillSimulator(
        slippage=FixedBpsSlippage(0.0),
        commission=BpsCommission(bps=0.0),
        max_participation=Decimal("1"),
    )
    order = Order(
        order_id="o1", intent_ref="i1", side="BUY", qty=Decimal("10"),
        order_type="MARKET", status="PENDING",
    )
    broker.submit(order)

    # bar 1: only 6 units of volume available -> partial fill
    working = broker.working_orders()
    assert len(working) == 1
    fill_1 = simulator.fill(working[0], fill_bar=_bar(1, volume=6.0))
    assert fill_1.fill_qty == Decimal("6")
    assert fill_1.partial is True
    broker.mark_filled(working[0].order_id, filled_qty=fill_1.fill_qty, status="PARTIALLY_FILLED")

    # the order remaining in the book must now ask for only the shortfall (4), not 10 again
    working = broker.working_orders()
    assert len(working) == 1
    assert working[0].qty == Decimal("4")
    assert working[0].status == "PARTIALLY_FILLED"

    # bar 2: plenty of volume -> fills exactly the remainder, not another 10
    fill_2 = simulator.fill(working[0], fill_bar=_bar(2, volume=100.0))
    assert fill_2.fill_qty == Decimal("4")
    assert fill_2.partial is False
    broker.mark_filled(working[0].order_id, filled_qty=fill_2.fill_qty, status="FILLED")

    assert broker.working_orders() == []
    total_filled = fill_1.fill_qty + fill_2.fill_qty
    assert total_filled == order.qty  # exactly the original request, never more
