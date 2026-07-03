"""The onboarding gate (docs/13 M18): while first-run setup is in progress,
every page request gets a plain-language status screen instead of the real
dashboard -- never raw stdout, never a stack trace, and it becomes reachable
again automatically the moment setup finishes. `/api/launch-status` and the
static theme/viz3d mounts stay reachable throughout so the status page can
render and poll.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from lqe.live.control import ControlPlane
from lqe.ops.jobs import LaunchState
from lqe.storage.state_reader import StateReader
from lqe.ui.app import create_app
from lqe.ui.data import DeskData


def _client(launch_state: LaunchState | None) -> TestClient:
    desk = DeskData(state_reader=StateReader([]), control=ControlPlane())
    return TestClient(create_app(desk, launch_state=launch_state))


def test_no_launch_state_serves_the_real_dashboard_immediately() -> None:
    client = _client(None)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Model Floor" in resp.text


def test_not_ready_serves_the_onboarding_screen_not_the_dashboard() -> None:
    state = LaunchState(ready=False, message="Preparing data...")
    client = _client(state)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Preparing data..." in resp.text
    assert "Model Floor" not in resp.text
    # honesty invariant carried over from the rest of the desk: no raw
    # traceback/console-looking text leaks into a designed status state.
    assert "Traceback" not in resp.text


def test_ready_serves_the_real_dashboard() -> None:
    state = LaunchState(ready=True, message="ready")
    client = _client(state)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Model Floor" in resp.text


def test_launch_status_endpoint_is_exempt_from_the_gate() -> None:
    state = LaunchState(ready=False, message="Still working...")
    client = _client(state)
    resp = client.get("/api/launch-status")
    assert resp.status_code == 200
    assert resp.json() == {"ready": False, "message": "Still working..."}


def test_becomes_ready_mid_session_without_restarting_the_server() -> None:
    state = LaunchState(ready=False, message="Setting up...")
    client = _client(state)
    assert "Setting up..." in client.get("/").text

    state.ready = True  # the launcher's background thread would flip this
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Model Floor" in resp.text


def test_no_launch_status_reports_ready_when_launch_state_is_absent() -> None:
    client = _client(None)
    resp = client.get("/api/launch-status")
    assert resp.json() == {"ready": True, "message": "ready"}
