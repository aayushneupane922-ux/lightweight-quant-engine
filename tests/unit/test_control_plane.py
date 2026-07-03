"""`ControlPlane` (docs/11 §11.9, GUARDRAILS.md): the UI's only write path.
Whitelisted commands only; KILL flips the persistent switch the risk model
reads; clearing a kill needs a named human operator and isn't reachable via
the generic command path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lqe.core.events import OrderIntent
from lqe.live.control import ControlPlane
from lqe.risk.kill_switch import KillSwitch
from lqe.risk.model import RiskModel
from lqe.risk.rules import PortfolioState


def _buy_intent(qty: str = "1") -> OrderIntent:
    return OrderIntent(
        intent_id="i1", signal_ref="s1", strategy="trend_ma_cross", symbol="BTC-USDT",
        side="BUY", qty=Decimal(qty), order_type="MARKET", idempotency_key="k1", reason="entry",
    )


def _state() -> PortfolioState:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return PortfolioState(
        symbol="BTC-USDT", equity=Decimal("10000"), cash=Decimal("10000"),
        peak_equity=Decimal("10000"), daily_pnl=Decimal("0"), position_qty=Decimal("0"),
        reference_price=Decimal("100"), last_data_ts=now, now_ts=now,
    )


def test_only_whitelisted_commands_are_accepted() -> None:
    plane = ControlPlane()
    with pytest.raises(ValueError, match="not a whitelisted control command"):
        plane.submit("DO_SOMETHING_BAD", source="ui", operator="alice")  # type: ignore[arg-type]


def test_kill_command_flips_the_switch_a_risk_model_reads() -> None:
    switch = KillSwitch.in_memory()
    plane = ControlPlane(kill_switch=switch)
    risk = RiskModel(kill_switch=switch)  # same switch instance -> shared state

    assert risk.check(_buy_intent(), _state()).verdict != "REJECT"
    plane.submit("KILL", source="ui", operator="alice", note="manual halt")

    assert plane.kill_active is True
    # a risk-increasing BUY is now rejected by the shared kill switch
    assert risk.check(_buy_intent(), _state()).verdict == "REJECT"


def test_clear_kill_requires_a_named_operator() -> None:
    switch = KillSwitch.in_memory()
    plane = ControlPlane(kill_switch=switch)
    plane.submit("KILL", source="ui", operator="alice")

    with pytest.raises(ValueError, match="named operator"):
        plane.clear_kill(operator="")

    plane.clear_kill(operator="alice")
    assert plane.kill_active is False


def test_every_command_is_audited() -> None:
    plane = ControlPlane()
    plane.submit("FREEZE", source="ui", operator="alice", note="lunch")
    plane.submit("START", source="ui", operator="alice")
    log = plane.log()
    assert [e.command for e in log] == ["FREEZE", "START"]
    assert all(e.operator == "alice" for e in log)
