"""The "Engine Room" conversation feed (docs/13 M21): the Intel view's
turn-by-turn dialogue between Strategist/Optimizer/Judge/Autopilot/Risk,
its read-only `/api/conversation` API, and the deterministic timeline
scrubber.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from lqe.core.engine import AuditLog
from lqe.core.events import (
    ControlEvent,
    DeRiskEvent,
    HypothesisEvent,
    NarrationEvent,
    PromotionEvent,
    TrialEvent,
    ValidationEvent,
)
from lqe.live.control import ControlPlane
from lqe.storage.state_reader import StateReader
from lqe.ui.app import create_app
from lqe.ui.data import DeskData

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _full_loop_log() -> AuditLog:
    log = AuditLog()
    seq = 1
    log.append(
        event_type="HypothesisEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=HypothesisEvent(
            hypo_id="h1", rationale="Volatility on BTC is climbing.",
            target_models=["breakout_x"], proposed_space={}, regime="trending",
        ),
    )
    seq += 1
    log.append(
        event_type="TrialEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=TrialEvent(
            trial_id="t0", hypo_id="h1", study_id="s1", params={"lookback": 48},
            oos_metric=1.42, seed=1, index=0,
        ),
    )
    seq += 1
    log.append(
        event_type="ValidationEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=ValidationEvent(
            candidate_id="cand:breakout_x:1", result="FAIL", dsr=0.10, pbo=0.71,
            cost_survived=True, beats_equal_weight=False, evidence={},
        ),
    )
    seq += 1
    log.append(
        event_type="NarrationEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=NarrationEvent(text="Discarding this idea, moving on."),
    )
    seq += 1
    log.append(
        event_type="ControlEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=ControlEvent(command="KILL", source="ui", operator="alice", note="manual halt"),
    )
    seq += 1
    log.append(
        event_type="DeRiskEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=DeRiskEvent(reason="drawdown breach", models=["breakout_x"], action="PAUSE"),
    )
    seq += 1
    log.append(
        event_type="PromotionEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
        payload=PromotionEvent(
            candidate_id="cand:trend_ma_cross:1", from_book="sandbox", to_book="tracked",
            config_version="v1",
        ),
    )
    return log


def _client_with_conversation() -> TestClient:
    data = DeskData(state_reader=StateReader(_full_loop_log().records), control=ControlPlane())
    return TestClient(create_app(data))


def _empty_client() -> TestClient:
    data = DeskData(state_reader=StateReader([]), control=ControlPlane())
    return TestClient(create_app(data))


def test_intel_view_renders_the_conversation_feed() -> None:
    html = _client_with_conversation().get("/intel").text
    assert 'id="convo-feed"' in html
    assert "Strategist" in html and "Optimizer" in html and "Judge" in html
    assert "Autopilot" in html and "Risk" in html


def test_intel_view_renders_the_timeline_scrubber() -> None:
    html = _client_with_conversation().get("/intel").text
    assert 'id="convo-scrubber"' in html
    assert 'id="convo-seq-label"' in html


def test_intel_view_empty_state_when_no_autonomy_events() -> None:
    html = _empty_client().get("/intel").text
    assert 'id="convo-empty"' in html
    assert "No autonomy steps recorded yet" in html


def test_intel_view_still_shows_the_existing_decision_cards_section() -> None:
    # M21 adds the conversation feed alongside the existing per-hypothesis
    # summary cards (M9), not instead of them.
    html = _client_with_conversation().get("/intel").text
    assert "Per-hypothesis summary" in html
    assert 'class="cards"' in html


def test_api_conversation_returns_the_full_dialogue() -> None:
    payload = _client_with_conversation().get("/api/conversation").json()
    participants = [m["participant"] for m in payload["messages"]]
    expected = ["Strategist", "Optimizer", "Judge", "Autopilot", "Risk", "Risk", "Judge"]
    assert participants == expected


def test_api_conversation_at_seq_replays_a_prefix() -> None:
    client = _client_with_conversation()
    full = client.get("/api/conversation").json()
    mid = client.get(f"/api/conversation?at_seq={full['messages'][1]['seq']}").json()
    assert len(mid["messages"]) <= len(full["messages"])
    assert mid["max_seq"] == full["max_seq"]


def test_api_conversation_empty_session_returns_empty_list() -> None:
    payload = _empty_client().get("/api/conversation").json()
    assert payload["messages"] == []


def test_pause_kill_reachable_from_the_intel_view() -> None:
    # the status rail (with KILL + AUTOPILOT controls) renders on every
    # page via base.html -- Intel is no exception.
    html = _client_with_conversation().get("/intel").text
    assert 'id="kill-btn"' in html
    assert 'id="autopilot-btn"' in html
