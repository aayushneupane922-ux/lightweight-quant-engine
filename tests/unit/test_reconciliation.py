"""docs/10 M5: reconciliation halts on injected mismatch; rebuild-from-
audit reproduces state from nothing but a persisted audit log.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from lqe.core.clock import ReplayClock
from lqe.core.engine import Engine
from lqe.core.errors import ReconciliationError
from lqe.core.events import FillEvent, OrderIntent, RiskDecision
from lqe.core.make_order import make_order
from lqe.risk.reconciliation import FillRecord, rebuild_from_audit, reconcile, replay_fills

SYMBOL = "BTC-USDT"
TS = datetime(2026, 1, 1, tzinfo=UTC)


def _fill(px: str, qty: str, fee: str = "0", order_id: str = "o1") -> FillEvent:
    return FillEvent(
        order_id=order_id, fill_ts=TS, fill_px=Decimal(px), fill_qty=Decimal(qty),
        fee=Decimal(fee), slippage_bps=0.0, partial=False,
    )


def test_reconcile_passes_when_ledger_matches_replay() -> None:
    starting_cash = Decimal("10000")
    fills: list[FillRecord] = [("BUY", _fill("100", "10")), ("SELL", _fill("110", "5"))]
    live = replay_fills(starting_cash=starting_cash, symbol=SYMBOL, fills=fills)
    reconcile(live=live, starting_cash=starting_cash, symbol=SYMBOL, fills=fills)  # must not raise


def test_reconcile_halts_on_injected_mismatch() -> None:
    starting_cash = Decimal("10000")
    fills: list[FillRecord] = [("BUY", _fill("100", "10"))]
    live = replay_fills(starting_cash=starting_cash, symbol=SYMBOL, fills=fills)
    live.cash += Decimal("1")  # inject a bug: cash drifted from what the fills justify
    with pytest.raises(ReconciliationError):
        reconcile(live=live, starting_cash=starting_cash, symbol=SYMBOL, fills=fills)


def test_reconcile_halts_on_a_missing_fill() -> None:
    starting_cash = Decimal("10000")
    all_fills: list[FillRecord] = [("BUY", _fill("100", "10")), ("BUY", _fill("100", "5"))]
    live = replay_fills(starting_cash=starting_cash, symbol=SYMBOL, fills=all_fills)
    # the caller only remembers the first fill -> replay disagrees with the live ledger
    with pytest.raises(ReconciliationError):
        reconcile(live=live, starting_cash=starting_cash, symbol=SYMBOL, fills=all_fills[:1])


def test_rebuild_from_audit_reproduces_state(tmp_path: Path) -> None:
    starting_cash = Decimal("10000")
    engine = Engine(run_id="rebuild-test", book="sandbox", clock=ReplayClock([TS]))
    engine.tick()

    intent = OrderIntent(
        intent_id="i1", signal_ref="s1", strategy="test", symbol=SYMBOL, side="BUY",
        qty=Decimal("10"), order_type="MARKET", idempotency_key="k1", reason="test",
    )
    decision = RiskDecision(intent_ref="i1", verdict="APPROVE", approved_qty=Decimal("10"))
    order = make_order(intent, decision)
    engine.emit("Order", order)
    engine.emit("FillEvent", _fill("100", "10", order_id=order.order_id))

    audit_path = tmp_path / "audit.jsonl"
    engine.audit.write_jsonl(audit_path)

    rebuilt = rebuild_from_audit(audit_path, starting_cash=starting_cash, symbol=SYMBOL)
    assert rebuilt.position_qty(SYMBOL) == Decimal("10")
    assert rebuilt.cash == starting_cash - Decimal("1000")


def test_rebuild_from_audit_rejects_a_fill_for_an_unknown_order(tmp_path: Path) -> None:
    engine = Engine(run_id="rebuild-test-2", book="sandbox", clock=ReplayClock([TS]))
    engine.tick()
    engine.emit("FillEvent", _fill("100", "10"))  # no matching Order event was ever emitted

    audit_path = tmp_path / "audit.jsonl"
    engine.audit.write_jsonl(audit_path)

    with pytest.raises(ReconciliationError):
        rebuild_from_audit(audit_path, starting_cash=Decimal("10000"), symbol=SYMBOL)
