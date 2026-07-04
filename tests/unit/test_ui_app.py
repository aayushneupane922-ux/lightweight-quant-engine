"""The desk's read endpoints (docs/11 §11.9): every view renders, the JSON
snapshot/tape APIs are read-only mirrors of the StateReader, and the
WebSocket streams a snapshot+tape frame.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from lqe.core.engine import AuditLog
from lqe.core.events import ControlEvent, MarketEvent
from lqe.live.control import ControlPlane
from lqe.storage.state_reader import CatalogModelInfo, StateReader
from lqe.ui.app import create_app
from lqe.ui.data import CatalogRow, DeskData


def _client() -> TestClient:
    data = DeskData(state_reader=StateReader([]), control=ControlPlane())
    return TestClient(create_app(data))


@pytest.mark.parametrize("page", ["/", "/catalog", "/research", "/risk", "/daily"])
def test_all_views_render(page: str) -> None:
    assert _client().get(page).status_code == 200


def test_status_rail_shows_every_symbols_feed_health_not_just_the_first() -> None:
    # V5 M27: `data_health` has been list-shaped since before this
    # milestone; the status rail template used to hardcode `[0]`.
    from decimal import Decimal

    log = AuditLog()
    for i, (symbol, price) in enumerate([("BTC-USDT", "100"), ("ETH-USDT", "10")]):
        log.append(
            event_type="MarketEvent", run_id="r", seq=i + 1, book="sandbox",
            sim_ts=datetime(2026, 1, 1, tzinfo=UTC),
            payload=MarketEvent(
                exchange="binance", symbol=symbol, timeframe="1m",
                ts_open=datetime(2026, 1, 1, tzinfo=UTC),
                o=Decimal(price), h=Decimal(price), l=Decimal(price), c=Decimal(price),
                v=1.0, source_version="test",
            ),
        )
    data = DeskData(state_reader=StateReader(log.records), control=ControlPlane())
    html = TestClient(create_app(data)).get("/").text
    assert "BTC-USDT" in html and "ETH-USDT" in html


def test_catalog_view_and_floor_snapshot_both_show_the_sleeve_not_just_family() -> None:
    # docs/14 (v4): sleeve, not family, is the catalog's actual
    # diversification unit -- both surfaces that list models by family
    # must also carry the sleeve, not silently drop it.
    catalog = [
        CatalogModelInfo(model_id="trend_ma_cross", family="trend", sleeve="trend_momentum"),
    ]
    data = DeskData(
        state_reader=StateReader([], catalog=catalog),
        control=ControlPlane(),
        catalog_rows=[
            CatalogRow(
                model_id="trend_ma_cross", family="trend", sleeve="trend_momentum",
                one_liner="MA cross.", oss_libs=["own"], status="unproven",
            )
        ],
    )
    client = TestClient(create_app(data))

    catalog_html = client.get("/catalog").text
    assert "Sleeve" in catalog_html
    assert "trend_momentum" in catalog_html

    snapshot = client.get("/api/snapshot").json()
    assert snapshot["models"][0]["sleeve"] == "trend_momentum"


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


def test_ws_frames_are_cached_per_reader_and_carry_the_seq() -> None:
    """perf phase 4: pings between live polls reuse one serialized frame
    (the reader is immutable, so the frame can't change until the live loop
    swaps a new reader in); `seq` lets the client skip repaints too."""
    data = DeskData(state_reader=StateReader([]), control=ControlPlane())
    client = TestClient(create_app(data))
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_text()
        ws.send_text("refresh")
        second = ws.receive_text()
        assert second == first  # identical string, not just equal payloads
        assert json.loads(first)["seq"] == 0

        log = AuditLog()
        log.append(
            event_type="ControlEvent", run_id="r", seq=1, book="sandbox",
            sim_ts=datetime(2026, 1, 1, tzinfo=UTC),
            payload=ControlEvent(command="START", source="live-loop", operator="t", note="new"),
        )
        data.set_state_reader(StateReader(log.records))
        ws.send_text("refresh")
        third = json.loads(ws.receive_text())
        assert third["seq"] == 1  # reader swap invalidates the cached frame
        assert len(third["tape"]) == 1


def test_theme_assets_are_served() -> None:
    client = _client()
    assert client.get("/theme/desk.css").status_code == 200
    assert client.get("/theme/desk.js").status_code == 200


def test_set_state_reader_swaps_what_the_api_serves_live() -> None:
    """post-v1.0 live-refresh extension: a background loop can replace the
    read side after construction and every existing read route picks up the
    new data immediately -- no route/template change needed."""
    data = DeskData(state_reader=StateReader([]), control=ControlPlane())
    client = TestClient(create_app(data))
    assert client.get("/api/tape?after_seq=0").json() == []

    log = AuditLog()
    log.append(
        event_type="ControlEvent", run_id="r", seq=1, book="sandbox",
        sim_ts=datetime(2026, 1, 1, tzinfo=UTC),
        payload=ControlEvent(command="START", source="live-loop", operator="t", note="grew"),
    )
    data.set_state_reader(StateReader(log.records))

    tape = client.get("/api/tape?after_seq=0").json()
    assert len(tape) == 1
    assert tape[0]["type"] == "ControlEvent"
