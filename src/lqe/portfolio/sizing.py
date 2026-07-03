"""Fixed-fractional position sizing (HANDOFF.md §6: MVP sizing is fixed-
fractional/vol-target, no portfolio-optimization layer yet). An EXIT signal
always sizes to fully flatten the current position; an ENTER signal targets
a fixed fraction of current equity.
"""

from __future__ import annotations

from decimal import Decimal

from lqe.core.events import SignalEvent


class FixedFractionalSizer:
    def __init__(self, *, fraction: Decimal = Decimal("0.1")) -> None:
        self._fraction = fraction

    def size(
        self, *, signal: SignalEvent, equity: Decimal, price: Decimal, current_qty: Decimal
    ) -> Decimal:
        if signal.intent_kind == "EXIT":
            return current_qty
        if price <= 0:
            return Decimal("0")
        target_notional = equity * self._fraction
        return (target_notional / price).quantize(Decimal("0.00000001"))
