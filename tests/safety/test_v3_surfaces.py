"""M22 hardening: extends safety coverage to the three v3 surfaces that
introduced new UI/plumbing (docs/13 §M18/M20/M21) -- the GUI job launcher,
the trade blotter, and the Engine Room conversation feed. Each must still
honor the 9 non-negotiables: no Order path outside `make_order`, kill
reachable from every new page, read-only APIs, no CLI/stdout.
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
JOBS_PY = SRC_ROOT / "ops" / "jobs.py"
DESK_JS = SRC_ROOT / "ui" / "theme" / "desk.js"


def _autopilot_reader() -> StateReader:
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


def _client(reader: StateReader | None = None, control: ControlPlane | None = None) -> TestClient:
    data = DeskData(state_reader=reader or StateReader([]), control=control or ControlPlane())
    return TestClient(create_app(data))


# --- launcher (M18 ops/jobs.py) -----------------------------------------


def test_job_manager_constructs_no_order_directly() -> None:
    tree = ast.parse(JOBS_PY.read_text(encoding="utf-8"), filename=str(JOBS_PY))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
        assert name not in ("Order", "PaperBroker"), (
            "ops/jobs.py must delegate to backtest.runner/live.session, "
            "never construct Order/PaperBroker directly"
        )


def test_job_manager_imports_no_autonomy_or_execution_internals() -> None:
    # ops/jobs.py legitimately threads a KillSwitch through to LiveSession
    # (lqe.risk.kill_switch is the sanctioned exception); it must not reach
    # into lqe.execution or lqe.autonomy directly -- those stay behind
    # backtest.runner/live.session, which already apply the promotion/risk
    # gate.
    text = JOBS_PY.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(JOBS_PY))
    offenders = []
    for node in ast.walk(tree):
        mod = ""
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
        elif isinstance(node, ast.Import):
            mod = node.names[0].name
        if mod.startswith("lqe.execution") or mod.startswith("lqe.autonomy"):
            offenders.append(mod)
    assert not offenders, f"ops/jobs.py reached past its boundary: {offenders}"


def test_job_manager_live_start_only_ever_wires_a_data_adapter() -> None:
    # the "adapter"/"csv_path"/"exchange" params on start_live() select a
    # *market-data* source only (CsvReplayAdapter/CcxtMarketDataAdapter);
    # there is no execution-adapter parameter anywhere on this surface.
    text = JOBS_PY.read_text(encoding="utf-8")
    assert "CsvReplayAdapter" in text and "CcxtMarketDataAdapter" in text
    assert "ExecutionAdapter" not in text
    assert "execution_adapter" not in text


# --- blotter (M20) --------------------------------------------------------


def test_kill_button_is_reachable_from_the_blotter() -> None:
    html = _client().get("/blotter").text
    assert 'id="kill-btn"' in html


def test_blotter_page_carries_the_paper_shield_and_no_raw_console() -> None:
    html = _client().get("/blotter").text
    assert "PAPER · LIVE LOCKED" in html
    assert "<pre" not in html.lower()
    assert "<textarea" not in html.lower()


def test_api_blotter_is_read_only() -> None:
    # only a GET route exists; no POST/PUT/DELETE handler is registered
    client = _client()
    resp = client.post("/api/blotter", json={})
    assert resp.status_code in (404, 405)


def test_blotter_route_renders_from_state_reader_only_no_order_construction() -> None:
    # docs/11 §11.1: the blotter is reconstructed read-only from events
    # already in the audit log -- confirm ui/data.py's delegator and
    # ui/app.py's route build no Order (the broader ui_boundary.py AST scan
    # already covers this repo-wide; this pins it specifically for the new
    # blotter surface so a future edit to just these two files still fails).
    for path in (SRC_ROOT / "ui" / "data.py", SRC_ROOT / "ui" / "app.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
            assert name != "Order", f"{path.name} constructs Order directly"


# --- conversation / Engine Room (M21) ------------------------------------


def test_kill_button_is_reachable_from_the_engine_room() -> None:
    html = _client().get("/intel").text
    assert 'id="kill-btn"' in html


@pytest.mark.filterwarnings("ignore")
def test_api_conversation_is_read_only_and_supports_deterministic_replay() -> None:
    client = _client(_autopilot_reader())
    full = client.get("/api/conversation").json()
    assert full["messages"], "expected at least one conversation message from a real campaign"
    early = client.get("/api/conversation?at_seq=5").json()
    assert early["at_seq"] == 5
    assert len(early["messages"]) <= len(full["messages"])
    # same seq -> identical payload (deterministic replay)
    assert client.get("/api/conversation?at_seq=5").json() == early


def test_api_conversation_has_no_write_method() -> None:
    resp = _client().post("/api/conversation", json={})
    assert resp.status_code in (404, 405)


def test_conversation_feed_js_never_posts_to_the_control_or_jobs_write_paths() -> None:
    # desk.js is shared across pages and legitimately POSTs to /api/control
    # and /api/jobs/* elsewhere (M18's whitelisted control path); the
    # conversation-feed-specific functions must stay strictly read (GET).
    # paintConversation/loadConversation/initConversationScrubber are the
    # three M21 functions, defined contiguously right before `apply`, the
    # next unrelated function -- slice exactly that span.
    text = DESK_JS.read_text(encoding="utf-8")
    start = text.index("function paintConversation")
    end = text.index("function apply(payload)")
    convo_span = text[start:end]
    assert "POST" not in convo_span
    assert "/api/control" not in convo_span
    assert "/api/jobs" not in convo_span
