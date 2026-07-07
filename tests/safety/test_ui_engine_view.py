"""The Engine (3D neural-web) view (docs/10 M10): the scene assets serve,
`/api/graph` is a read-only mirror with deterministic replay, the view
carries honesty overlays and constructs no Order, and the viz3d frontend
imports no risk/execution internals.
"""

from __future__ import annotations

import ast
import json
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


# -- docs/15 V5 M29: the diversification panel (dated offline report) ------


def test_engine_view_shows_an_honest_empty_state_when_not_yet_computed() -> None:
    html = _client_with_audit().get("/engine").text
    assert "Not yet computed" in html
    assert "diversification_report.py" in html


def test_engine_view_shows_the_dated_diversification_panel_when_present(tmp_path: Path) -> None:
    artifact = tmp_path / "diversification_score.json"
    artifact.write_text(
        json.dumps(
            {
                "computed_at": "2026-07-04T12:00:00+00:00",
                "n_bars": 2000,
                "universe": ["BTC-USDT"],
                "n_models": 42,
                "average_pairwise_correlation": 0.257,
                "effective_number_of_bets": 6.5,
                "n_sleeves": 9,
                "dominant_sleeve": "trend_momentum",
                "max_sleeve_share": 0.31,
            }
        )
    )
    data = DeskData(
        state_reader=StateReader([]), control=ControlPlane(), diversification_path=artifact,
    )
    html = TestClient(create_app(data)).get("/engine").text
    assert "6.50" in html  # effective_number_of_bets
    assert "0.257" in html  # average_pairwise_correlation
    assert "trend_momentum" in html
    assert "2026-07-04T12:00:00+00:00" in html
    assert "computed offline" in html


def test_api_diversification_route_mirrors_the_desk_payload(tmp_path: Path) -> None:
    artifact = tmp_path / "diversification_score.json"
    artifact.write_text(
        json.dumps(
            {
                "computed_at": "2026-07-04T12:00:00+00:00",
                "n_bars": 2000, "universe": ["BTC-USDT"],
                "n_models": 42, "average_pairwise_correlation": 0.257,
                "effective_number_of_bets": 6.5, "n_sleeves": 9,
                "dominant_sleeve": "trend_momentum", "max_sleeve_share": 0.31,
            }
        )
    )
    data = DeskData(
        state_reader=StateReader([]), control=ControlPlane(), diversification_path=artifact,
    )
    body = TestClient(create_app(data)).get("/api/diversification").json()
    assert body["computed"] is True
    assert body["n_models"] == 42
    assert body["dominant_sleeve"] == "trend_momentum"


def test_diversification_is_an_honest_empty_state_when_the_path_is_missing(tmp_path: Path) -> None:
    data = DeskData(
        state_reader=StateReader([]), control=ControlPlane(),
        diversification_path=tmp_path / "does-not-exist.json",
    )
    payload = data.diversification()
    assert payload.computed is False
    assert "Not yet computed" in payload.reason


def test_diversification_empty_state_when_the_file_is_malformed(tmp_path: Path) -> None:
    artifact = tmp_path / "bad.json"
    artifact.write_text("{not valid json")
    data = DeskData(
        state_reader=StateReader([]), control=ControlPlane(), diversification_path=artifact,
    )
    payload = data.diversification()
    assert payload.computed is False
    assert "unreadable or malformed" in payload.reason


def test_diversification_refreshes_when_the_artifact_is_rewritten(tmp_path: Path) -> None:
    artifact = tmp_path / "diversification_score.json"
    artifact.write_text(json.dumps({
        "computed_at": "t1", "n_models": 10, "average_pairwise_correlation": 0.5,
        "effective_number_of_bets": 2.0, "n_sleeves": 3,
        "dominant_sleeve": "a", "max_sleeve_share": 0.5,
    }))
    data = DeskData(
        state_reader=StateReader([]), control=ControlPlane(), diversification_path=artifact,
    )
    first = data.diversification()
    assert first.n_models == 10
    # a re-run of the script overwrites the file with new numbers -- the
    # mtime-checked cache must pick this up without restarting the desk.
    import os
    import time
    time.sleep(0.01)
    artifact.write_text(json.dumps({
        "computed_at": "t2", "n_models": 99, "average_pairwise_correlation": 0.1,
        "effective_number_of_bets": 8.0, "n_sleeves": 5,
        "dominant_sleeve": "b", "max_sleeve_share": 0.2,
    }))
    os.utime(artifact, None)
    second = data.diversification()
    assert second.n_models == 99
