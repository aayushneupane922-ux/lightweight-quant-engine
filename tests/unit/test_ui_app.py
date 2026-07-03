"""The desk's read endpoints (docs/11 §11.9): every view renders, the JSON
snapshot/tape APIs are read-only mirrors of the StateReader, and the
WebSocket streams a snapshot+tape frame.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from lqe.live.control import ControlPlane
from lqe.storage.state_reader import StateReader
from lqe.ui.app import create_app
from lqe.ui.data import DeskData


def _client() -> TestClient:
    data = DeskData(state_reader=StateReader([]), control=ControlPlane())
    return TestClient(create_app(data))


@pytest.mark.parametrize("page", ["/", "/catalog", "/research", "/risk", "/daily"])
def test_all_views_render(page: str) -> None:
    assert _client().get(page).status_code == 200


def test_snapshot_api_is_read_only_and_marks_simulated() -> None:
    snap = _client().get("/api/snapshot").json()
    assert snap["simulated"] is True
    assert snap["kill_active"] is False


def test_tape_api_supports_incremental_after_seq() -> None:
    client = _client()
    assert client.get("/api/tape?after_seq=0").json() == []  # empty audit -> empty tape


def test_websocket_streams_a_snapshot_frame() -> None:
    with _client().websocket_connect("/ws") as ws:
        frame = json.loads(ws.receive_text())
        assert "snapshot" in frame and "tape" in frame
        assert frame["snapshot"]["simulated"] is True


def test_theme_assets_are_served() -> None:
    client = _client()
    assert client.get("/theme/desk.css").status_code == 200
    assert client.get("/theme/desk.js").status_code == 200
