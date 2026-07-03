"""The single `Order` constructor (docs/11 §11.2, GUARDRAILS.md).

No other module may construct an `Order`. Enforced by
`tests/safety/test_make_order_lockout.py` (AST scan of `src/lqe`).
"""

from __future__ import annotations

from lqe.core.errors import LockoutViolation
from lqe.core.events import Order, OrderIntent, RiskDecision


def make_order(intent: OrderIntent, decision: RiskDecision) -> Order:
    if decision.verdict == "REJECT":
        raise LockoutViolation(
            f"make_order called with a REJECT risk decision for intent {intent.intent_id!r}"
        )
    qty = decision.approved_qty if decision.verdict == "CLAMP" else intent.qty
    return Order(
        order_id=f"order:{intent.intent_id}",
        intent_ref=intent.intent_id,
        side=intent.side,
        qty=qty,
        order_type=intent.order_type,
        limit_px=intent.limit_px,
        status="PENDING",
    )
