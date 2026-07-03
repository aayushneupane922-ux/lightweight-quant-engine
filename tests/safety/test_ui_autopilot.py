"""The autopilot control surface (docs/02 §2.3, docs/10 M9): the toggle
goes through the whitelisted ControlPlane; take-the-wheel disengages it;
and the human KILL is un-overridable — it forces autopilot off regardless.
Decision cards render read-only from the audit's autonomy events.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lqe.autonomy.optimizer import OptunaOptimizer
from lqe.autonomy.orchestrator import Orchestrator
from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
from lqe.autonomy.searchable import default_searchable_models
from lqe.autonomy.validator import Validator
from lqe.core.events import MarketEvent
from lqe.live.control import ControlPlane
from lqe.storage.state_reader import StateReader
from lqe.ui.app import create_app
from lqe.ui.data import DeskData

SYMBOL = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _autopilot_audit() -> StateReader:
    bars = []
    price = Decimal("100")
    for i in range(220):
        price = price + Decimal("1") if (i // 11) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=START + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    orch = Orchestrator(
        validator=Validator(n_folds=2, random_control_reps=3),
        gate=PromotionGate(thresholds=GateThresholds(min_periods=1, min_trades=1)),
        optimizer=OptunaOptimizer(), searchable_models=default_searchable_models(),
        bars=bars, symbol=SYMBOL, starting_cash=Decimal("10000"), seed=1, n_trials=4,
    )
    orch.run(steps=2, start=START)
    return StateReader(orch.engine.audit.records)


def _client(control: ControlPlane, reader: StateReader | None = None) -> TestClient:
    data = DeskData(state_reader=reader or StateReader([]), control=control)
    return TestClient(create_app(data))


def test_autopilot_toggles_through_the_control_plane() -> None:
    control = ControlPlane()
    client = _client(control)
    assert control.autopilot_on is False
    client.post("/api/control", json={"command": "AUTOPILOT_ON", "operator": "alice"})
    assert control.autopilot_on is True
    # take the wheel
    client.post("/api/control", json={"command": "AUTOPILOT_OFF", "operator": "alice"})
    assert control.autopilot_on is False


def test_kill_forces_autopilot_off_and_is_un_overridable() -> None:
    control = ControlPlane()
    client = _client(control)
    client.post("/api/control", json={"command": "AUTOPILOT_ON", "operator": "alice"})
    assert control.autopilot_on is True
    client.post("/api/control", json={"command": "KILL", "operator": "alice"})
    # kill wins: autopilot reads off while the kill is active, even though
    # AUTOPILOT_OFF was never sent
    assert control.autopilot_on is False
    assert control.kill_active is True


@pytest.mark.filterwarnings("ignore")
def test_intel_view_renders_decision_cards_from_the_audit() -> None:
    client = _client(ControlPlane(), _autopilot_audit())
    resp = client.get("/intel")
    assert resp.status_code == 200
    assert "Decision Cards" in resp.text
    assert "HYPOTHESIS" in resp.text and "VALIDATE" in resp.text


def test_autopilot_state_shows_in_the_status_rail() -> None:
    control = ControlPlane()
    client = _client(control)
    assert "AUTOPILOT OFF" in client.get("/").text
    client.post("/api/control", json={"command": "AUTOPILOT_ON", "operator": "alice"})
    assert "AUTOPILOT ON" in client.get("/").text
