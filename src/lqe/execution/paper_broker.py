"""The sole `ExecutionAdapter` (docs/archive/10 §10.15, docs/06 §6.6).

`is_paper = True`, asserted at every session's startup. Owns the working-
order book only; the actual fill matching against bar data is the session
loop's job (`backtest/make_session.py`), calling into `execution/fills.py`
one bar at a time — this is what lets a fill legally use only the bar that
arrives *after* the order was submitted (docs/archive/08 §8.2's bar-timing
rule), never the bar that produced the signal.
"""

from __future__ import annotations

from typing import Literal

from lqe.core.events import Order


class PaperBroker:
    is_paper: bool = True

    def __init__(self) -> None:
        self._working: dict[str, Order] = {}

    def submit(self, order: Order) -> None:
        self._working[order.order_id] = order.model_copy(update={"status": "ACCEPTED"})

    def cancel(self, order_id: str) -> None:
        self._working.pop(order_id, None)

    def working_orders(self) -> list[Order]:
        return [
            order
            for order in self._working.values()
            if order.status in ("ACCEPTED", "PARTIALLY_FILLED")
        ]

    def mark_filled(
        self, order_id: str, *, status: Literal["PARTIALLY_FILLED", "FILLED"]
    ) -> Order:
        order = self._working[order_id]
        updated = order.model_copy(update={"status": status})
        if status == "FILLED":
            del self._working[order_id]
        else:
            self._working[order_id] = updated
        return updated
