"""The GUI job-trigger HTTP surface (docs/13 M18): `/api/jobs*` lets the
dashboard start ingest/backtest/live sessions instead of requiring the CLI.
Exercised here via FastAPI's TestClient against a real `JobManager` wired to
an offline CSV fixture -- no real network, deterministic.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lqe.live.control import ControlPlane
from lqe.ops.jobs import JobManager
from lqe.risk.kill_switch import KillSwitch
from lqe.storage.state_reader import StateReader
from lqe.ui.app import create_app
from lqe.ui.data import DeskData

pytest.importorskip("optuna")

SYMBOL = "BTC-USDT"
N_BARS = 150


def _fixture_csv(tmp_path: Path) -> Path:
    now = datetime.now(UTC)
    rows = ["ts_open,open,high,low,close,volume"]
    price = 100.0
    for i in range(N_BARS):
        ts = now - timedelta(minutes=(N_BARS - i) + 5)
        close = 100.0 + 0.01 * i
        openp = price
        high = max(openp, close) + 0.5
        low = min(openp, close) - 0.5
        rows.append(
            f"{ts.isoformat()},{openp:.2f},{high:.2f},{low:.2f},{close:.2f},{10 + (i % 5)}"
        )
        price = close
    path = tmp_path / "fixture.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _client_with_jobs() -> tuple[TestClient, JobManager]:
    kill_switch = KillSwitch.in_memory()
    control = ControlPlane(kill_switch=kill_switch)
    desk = DeskData(state_reader=StateReader([]), control=control)
    jobs = JobManager(desk_data=desk, kill_switch=kill_switch)
    desk.jobs = jobs
    return TestClient(create_app(desk)), jobs


def test_api_jobs_returns_404_when_jobs_not_enabled() -> None:
    desk = DeskData(state_reader=StateReader([]), control=ControlPlane())
    client = TestClient(create_app(desk))
    resp = client.get("/api/jobs")
    assert resp.status_code == 404


def test_api_jobs_lists_all_three_idle_jobs() -> None:
    client, _jobs = _client_with_jobs()
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    names = {row["name"] for row in resp.json()}
    assert names == {"ingest", "backtest", "live"}


def test_api_jobs_ingest_triggers_a_real_ingest(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    client, jobs = _client_with_jobs()
    resp = client.post(
        "/api/jobs/ingest",
        json={
            "adapter": "csv", "exchange": "demo", "symbol": SYMBOL, "timeframe": "1m",
            "root": str(tmp_path / "data"), "csv_path": str(csv_path),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["started"] is True

    deadline = time.time() + 10
    while time.time() < deadline:
        status = next(s for s in jobs.statuses() if s.name == "ingest")
        if status.state != "running":
            break
        time.sleep(0.02)
    assert status.state == "done", status.message


def test_api_jobs_live_start_then_stop(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    client, jobs = _client_with_jobs()
    resp = client.post(
        "/api/jobs/live/start",
        json={
            "adapter": "csv", "exchange": "demo", "csv_path": str(csv_path), "symbol": SYMBOL,
            "timeframe": "1m", "poll_seconds": 0.05, "lookback_bars": 100,
            "starting_cash": 10_000.0, "autonomy_every": 1000, "n_trials": 1,
            "min_periods": 50, "use_llm": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["started"] is True

    deadline = time.time() + 10
    while time.time() < deadline:
        status = next(s for s in jobs.statuses() if s.name == "live")
        if "models trading" in status.message or status.state == "error":
            break
        time.sleep(0.02)
    assert status.state == "running", status.message

    stop_resp = client.post("/api/jobs/live/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["stopped"] is True


def test_api_jobs_live_stop_returns_false_when_nothing_running() -> None:
    client, _jobs = _client_with_jobs()
    resp = client.post("/api/jobs/live/stop")
    assert resp.status_code == 200
    assert resp.json()["stopped"] is False


def test_floor_and_research_render_the_control_panels_when_jobs_enabled() -> None:
    client, _jobs = _client_with_jobs()
    floor = client.get("/").text
    assert 'id="control-panel"' in floor
    assert 'id="live-toggle-btn"' in floor

    research = client.get("/research").text
    assert 'id="backtest-panel"' in research
    assert 'id="backtest-btn"' in research


def test_control_panels_absent_when_jobs_not_enabled() -> None:
    desk = DeskData(state_reader=StateReader([]), control=ControlPlane())
    client = TestClient(create_app(desk))
    assert 'id="control-panel"' not in client.get("/").text
    assert 'id="backtest-panel"' not in client.get("/research").text
