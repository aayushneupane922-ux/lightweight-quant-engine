"""The fill simulator (docs/archive/10 §10.5): pessimistic, next-bar-open by
default. The caller (the session loop) is responsible for only ever passing
a bar strictly after the one that produced the order — this module has no
opinion on *which* bar it's given, so that invariant lives in exactly one
place (`backtest/make_session.py`) and is tested there.
"""

from __future__ import annotations

from decimal import Decimal

from lqe.core.events import FillEvent, MarketEvent, Order
from lqe.execution.commission import BpsCommission
from lqe.execution.slippage import FixedBpsSlippage


class MarketOrderFillSimulator:
    def __init__(
        self,
        *,
        slippage: FixedBpsSlippage,
        commission: BpsCommission,
        max_participation: Decimal = Decimal("1"),
    ) -> None:
        self._slippage = slippage
        self._commission = commission
        self._max_participation = max_participation

    def fill(self, order: Order, *, fill_bar: MarketEvent) -> FillEvent:
        if order.order_type != "MARKET":
            raise ValueError("MarketOrderFillSimulator only fills MARKET orders")

        adjusted_px, slippage_bps = self._slippage.adjust(side=order.side, price=fill_bar.o)
        volume_cap = Decimal(str(fill_bar.v)) * self._max_participation
        fill_qty = min(order.qty, volume_cap) if volume_cap > 0 else order.qty
        fee = self._commission.compute(qty=fill_qty, price=adjusted_px)

        return FillEvent(
            order_id=order.order_id,
            fill_ts=fill_bar.ts_open,
            fill_px=adjusted_px,
            fill_qty=fill_qty,
            fee=fee,
            slippage_bps=slippage_bps,
            partial=fill_qty < order.qty,
        )
