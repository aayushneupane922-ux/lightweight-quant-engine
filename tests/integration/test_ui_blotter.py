"""The Blotter view + its read-only API surface (docs/13 M20): full order
lifecycle (intent -> risk decision -> fill/reject), one row per fill,
filters/tabs, an honest empty state, and a reconciliation panel.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.live.control import ControlPlane
from lqe.models.plugins.trend_ma_cross import TrendMaCross
from lqe.storage.state_reader import CatalogModelInfo, StateReader
from lqe.ui.app import create_app
from lqe.ui.data import DeskData

SYMBOL = "BTC-USDT"


def _bars(n: int) -> list[MarketEvent]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        price = price + Decimal("1") if (i // 10) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    return bars


def _client_with_trades() -> TestClient:
    session = run_backtest(
        run_id="blotter-ui", symbol=SYMBOL, bars=_bars(120),
        strategy=TrendMaCross(symbol=SYMBOL, fast=5, slow=20), starting_cash=Decimal("10000"),
    )
    reader = StateReader(
        session.engine.audit.records,
        catalog=[CatalogModelInfo(model_id="trend_ma_cross", family="trend")],
    )
    data = DeskData(state_reader=reader, control=ControlPlane())
    return TestClient(create_app(data))


def _empty_client() -> TestClient:
    data = DeskData(state_reader=StateReader([]), control=ControlPlane())
    return TestClient(create_app(data))


def test_blotter_view_renders_with_real_fills() -> None:
    html = _client_with_trades().get("/blotter").text
    assert 'id="blotter-table"' in html
    assert 'id="blotter-body"' in html
    assert "trend_ma_cross" in html


def test_blotter_view_shows_filters_and_sound_toggle() -> None:
    html = _client_with_trades().get("/blotter").text
    assert 'id="blotter-filter-model"' in html
    assert 'id="blotter-filter-symbol"' in html
    assert 'id="blotter-filter-side"' in html
    assert 'id="blotter-sound-toggle"' in html


def test_blotter_view_shows_reconciliation_panel() -> None:
    html = _client_with_trades().get("/blotter").text
    assert "Reconciliation" in html
    assert "Net qty" in html or "net qty" in html.lower()


def test_blotter_nav_entry_present_on_every_page() -> None:
    html = _client_with_trades().get("/").text
    assert 'href="/blotter"' in html
    assert ">Blotter<" in html


def test_blotter_empty_state_explains_why_not_a_blank_panel() -> None:
    html = _empty_client().get("/blotter").text
    assert 'id="blotter-empty"' in html
    assert "Warming up" in html
    # the table itself should be hidden, not rendered empty-and-confusing
    assert 'id="blotter-table" hidden' in html or 'hidden id="blotter-table"' in html


def test_api_blotter_returns_the_full_lifecycle_json() -> None:
    rows = _client_with_trades().get("/api/blotter").json()
    assert rows
    required = {"seq", "sim_ts", "model", "symbol", "side", "verdict"}
    assert all(required <= row.keys() for row in rows)


def test_api_blotter_after_seq_is_incremental() -> None:
    client = _client_with_trades()
    everything = client.get("/api/blotter?after_seq=0").json()
    highest = everything[-1]["seq"]
    assert client.get(f"/api/blotter?after_seq={highest}").json() == []


def test_api_blotter_empty_session_returns_empty_list() -> None:
    assert _empty_client().get("/api/blotter").json() == []


def test_websocket_frame_includes_blotter_rows() -> None:
    with _client_with_trades().websocket_connect("/ws") as ws:
        frame = json.loads(ws.receive_text())
        assert "blotter" in frame
        assert frame["blotter"]
        assert frame["blotter"][0]["model"] == "trend_ma_cross"
