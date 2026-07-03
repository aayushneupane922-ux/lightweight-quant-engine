"""The Engine (3D neural-web) view (docs/10 M10): the scene assets serve,
`/api/graph` is a read-only mirror with deterministic replay, the view
carries honesty overlays and constructs no Order, and the viz3d frontend
imports no risk/execution internals.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

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
SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "lqe"


def _client_with_audit() -> TestClient:
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
    data = DeskData(state_reader=StateReader(orch.engine.audit.records), control=ControlPlane())
    return TestClient(create_app(data))


@pytest.mark.filterwarnings("ignore")
def test_engine_view_renders_with_honesty_overlay() -> None:
    html = _client_with_audit().get("/engine").text
    assert 'id="web"' in html  # the scene canvas
    assert "PAPER · LIVE LOCKED" in html
    assert "SIMULATED" in html


def test_neural_web_scene_asset_is_served_from_viz3d() -> None:
    resp = _client_with_audit().get("/viz3d/neural_web.js")
    assert resp.status_code == 200
    assert "canvas" in resp.text.lower()


@pytest.mark.filterwarnings("ignore")
def test_api_graph_is_read_only_and_supports_deterministic_replay() -> None:
    client = _client_with_audit()
    full = client.get("/api/graph").json()
    assert full["simulated"] is True
    early = client.get("/api/graph?at_seq=5").json()
    assert early["at_seq"] == 5
    assert len(early["nodes"]) <= len(full["nodes"])
    # same seq -> identical payload (deterministic replay)
    assert client.get("/api/graph?at_seq=5").json() == early


def test_viz3d_scene_contains_no_command_posts() -> None:
    # the 3D view is read-only: it must not POST to the control write path
    js = (SRC_ROOT / "viz3d" / "neural_web.js").read_text(encoding="utf-8")
    assert "/api/control" not in js
    assert 'method: "POST"' not in js and "method:'POST'" not in js


def test_viz3d_package_imports_no_risk_execution_or_autonomy() -> None:
    # the only .py in viz3d is __init__; it must stay a docstring-only module
    for path in (SRC_ROOT / "viz3d").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            mod = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
            elif isinstance(node, ast.Import):
                mod = node.names[0].name
            assert not mod.startswith(("lqe.risk", "lqe.execution", "lqe.autonomy")), mod
