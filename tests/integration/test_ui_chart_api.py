"""The Floor hero chart's read-only data surface (docs/13 M19):
`/api/chart/price` and `/api/chart/equity` mirror `StateReader.price_series`/
`equity_curve`, same read-only contract as the pre-existing `/api/snapshot`
and `/api/tape`.
"""

from __future__ import annotations

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


def _client_with_data() -> TestClient:
    session = run_backtest(
        run_id="chart-api", symbol=SYMBOL, bars=_bars(120),
        strategy=TrendMaCross(symbol=SYMBOL, fast=5, slow=20), starting_cash=Decimal("10000"),
    )
    reader = StateReader(
        session.engine.audit.records,
        catalog=[CatalogModelInfo(model_id="trend_ma_cross", family="trend")],
    )
    data = DeskData(state_reader=reader, control=ControlPlane())
    return TestClient(create_app(data))


def test_chart_price_defaults_to_the_only_fed_symbol() -> None:
    rows = _client_with_data().get("/api/chart/price").json()
    assert len(rows) == 120
    assert all({"ts", "o", "h", "l", "c", "v"} <= row.keys() for row in rows)


def test_chart_price_accepts_an_explicit_symbol() -> None:
    client = _client_with_data()
    assert client.get(f"/api/chart/price?symbol={SYMBOL}").json()
    assert client.get("/api/chart/price?symbol=ETH-USDT").json() == []


def test_chart_price_respects_max_points() -> None:
    rows = _client_with_data().get("/api/chart/price?max_points=10").json()
    assert len(rows) <= 10


def test_chart_equity_returns_points() -> None:
    rows = _client_with_data().get("/api/chart/equity").json()
    assert rows, "expected a non-empty equity curve"
    assert all({"ts", "equity"} <= row.keys() for row in rows)


def test_chart_endpoints_on_an_empty_session_return_empty_lists() -> None:
    data = DeskData(state_reader=StateReader([]), control=ControlPlane())
    client = TestClient(create_app(data))
    assert client.get("/api/chart/price").json() == []
    assert client.get("/api/chart/equity").json() == []


def test_vendored_lightweight_charts_is_served() -> None:
    resp = _client_with_data().get("/theme/vendor/lightweight-charts.standalone.production.js")
    assert resp.status_code == 200
    assert "TradingView Lightweight Charts" in resp.text
    assert "Apache License 2.0" in resp.text


def test_chart_js_is_served() -> None:
    assert _client_with_data().get("/theme/chart.js").status_code == 200
