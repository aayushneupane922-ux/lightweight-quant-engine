"""`make_order` must be the only place `Order(...)` is constructed.

Static AST scan over every `.py` file in `src/lqe`, excluding
`core/make_order.py` itself, looking for a call whose callee resolves to the
name `Order`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from lqe.core.errors import LockoutViolation
from lqe.core.events import Order, OrderIntent, RiskDecision
from lqe.core.make_order import make_order

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "lqe"
ALLOWED_FILE = SRC_ROOT / "core" / "make_order.py"


def _calls_order_constructor(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
        if name == "Order":
            return True
    return False


def test_make_order_is_the_only_order_constructor() -> None:
    offenders = [
        path
        for path in SRC_ROOT.rglob("*.py")
        if path != ALLOWED_FILE and _calls_order_constructor(path)
    ]
    assert offenders == [], f"Order() constructed outside make_order.py in: {offenders}"


def test_make_order_builds_an_order_after_approve() -> None:
    intent = OrderIntent(
        intent_id="intent-1",
        signal_ref="signal-1",
        strategy="trend_ma_cross",
        symbol="BTC-USDT",
        side="BUY",
        qty="1.0",  # type: ignore[arg-type]
        order_type="MARKET",
        idempotency_key="idem-1",
        reason="test",
    )
    decision = RiskDecision(
        intent_ref="intent-1", verdict="APPROVE", approved_qty="1.0"  # type: ignore[arg-type]
    )
    order = make_order(intent, decision)
    assert isinstance(order, Order)
    assert order.status == "PENDING"
    assert order.qty == intent.qty


def test_make_order_rejects_a_reject_decision() -> None:
    intent = OrderIntent(
        intent_id="intent-2",
        signal_ref="signal-2",
        strategy="trend_ma_cross",
        symbol="BTC-USDT",
        side="SELL",
        qty="1.0",  # type: ignore[arg-type]
        order_type="MARKET",
        idempotency_key="idem-2",
        reason="test",
    )
    decision = RiskDecision(
        intent_ref="intent-2", verdict="REJECT", approved_qty="0"  # type: ignore[arg-type]
    )
    with pytest.raises(LockoutViolation):
        make_order(intent, decision)
