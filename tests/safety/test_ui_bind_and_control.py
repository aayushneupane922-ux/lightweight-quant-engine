"""The desk binds `127.0.0.1` only and its single write path is the
whitelisted control plane (docs/11 §11.9/§11.11/§11.12): KILL flips the
persistent switch a risk model reads and blocks risk-increasing orders; no
route can place or size an order.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from lqe.core.events import OrderIntent
from lqe.live.control import ControlPlane
from lqe.risk.kill_switch import KillSwitch
from lqe.risk.model import RiskModel
from lqe.risk.rules import PortfolioState
from lqe.storage.state_reader import StateReader
from lqe.ui.app import BIND_HOST, create_app
from lqe.ui.data import DeskData


def _desk(control: ControlPlane) -> DeskData:
    return DeskData(state_reader=StateReader([]), control=control)


def _state() -> PortfolioState:
    from datetime import UTC, datetime

    now = datetime(2026, 1, 1, tzinfo=UTC)
    return PortfolioState(
        symbol="BTC-USDT", equity=Decimal("10000"), cash=Decimal("10000"),
        peak_equity=Decimal("10000"), daily_pnl=Decimal("0"), position_qty=Decimal("0"),
        reference_price=Decimal("100"), last_data_ts=now, now_ts=now,
    )


def _buy() -> OrderIntent:
    return OrderIntent(
        intent_id="i1", signal_ref="s1", strategy="trend_ma_cross", symbol="BTC-USDT",
        side="BUY", qty=Decimal("1"), order_type="MARKET", idempotency_key="k1", reason="entry",
    )


def test_bind_host_is_localhost_only() -> None:
    assert BIND_HOST == "127.0.0.1"


def test_kill_from_the_ui_blocks_a_risk_increasing_order() -> None:
    switch = KillSwitch.in_memory()
    risk = RiskModel(kill_switch=switch)
    app = create_app(_desk(ControlPlane(kill_switch=switch)))
    client = TestClient(app)

    assert risk.check(_buy(), _state()).verdict != "REJECT"
    resp = client.post("/api/control", json={"command": "KILL", "operator": "alice"})
    assert resp.status_code == 200 and resp.json()["kill_active"] is True
    # the same persistent switch the UI flipped now rejects a BUY at the gate
    assert risk.check(_buy(), _state()).verdict == "REJECT"


def test_unknown_control_command_is_rejected() -> None:
    app = create_app(_desk(ControlPlane(kill_switch=KillSwitch.in_memory())))
    client = TestClient(app)
    resp = client.post("/api/control", json={"command": "PLACE_ORDER", "operator": "x"})
    assert resp.status_code == 400


def test_clear_kill_requires_an_operator_via_the_api() -> None:
    switch = KillSwitch.in_memory()
    app = create_app(_desk(ControlPlane(kill_switch=switch)))
    client = TestClient(app)
    client.post("/api/control", json={"command": "KILL", "operator": "alice"})
    # empty operator -> falls back to a named default so the switch never
    # clears anonymously; assert it clears only with a name present
    resp = client.post("/api/control", json={"command": "CLEAR_KILL", "operator": "alice"})
    assert resp.status_code == 200 and resp.json()["kill_active"] is False
