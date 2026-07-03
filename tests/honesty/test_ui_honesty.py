"""The GUI honesty contract (docs/05 §5.3, docs/11 §11.12): no raw CLI/
stdout is rendered; every page carries the PAPER·LIVE LOCKED shield and a
SIMULATED marker; model/experiment rows show sample size + unproven/
validated status; no profit-language anywhere.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.live.control import ControlPlane
from lqe.models.plugins.trend_ma_cross import TrendMaCross
from lqe.storage.state_reader import CatalogModelInfo, StateReader
from lqe.ui.app import create_app
from lqe.ui.data import CatalogRow, DeskData, ExperimentRow

SYMBOL = "BTC-USDT"
PAGES = ["/", "/catalog", "/research", "/risk", "/daily", "/blotter"]


def _client() -> TestClient:
    bars = []
    price = Decimal("100")
    for i in range(120):
        price = price + Decimal("1") if (i // 10) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    session = run_backtest(
        run_id="honesty", symbol=SYMBOL, bars=bars,
        strategy=TrendMaCross(symbol=SYMBOL, fast=5, slow=20), starting_cash=Decimal("10000"),
    )
    reader = StateReader(
        session.engine.audit.records,
        catalog=[CatalogModelInfo(model_id="trend_ma_cross", family="trend")],
    )
    data = DeskData(
        state_reader=reader,
        control=ControlPlane(),
        catalog_rows=[
            CatalogRow(
                model_id="trend_ma_cross", family="trend", one_liner="MA cross.",
                oss_libs=["own"], status="unproven",
            )
        ],
        experiment_rows=[
            ExperimentRow(
                run_id="r1", strategy="trend_ma_cross", sharpe=0.4, dsr=0.1, pbo=0.6,
                max_dd=0.12, n_trades=15, cost_bps=10.0, passed_gate=False,
            )
        ],
    )
    return TestClient(create_app(data))


@pytest.mark.parametrize("page", PAGES)
def test_every_page_carries_the_paper_lockout_shield(page: str) -> None:
    html = _client().get(page).text
    assert "PAPER · LIVE LOCKED" in html


@pytest.mark.parametrize("page", PAGES)
def test_no_page_renders_a_raw_console_or_stdout_dump(page: str) -> None:
    html = _client().get(page).text.lower()
    # a CLI feed would show up as a <pre> block or a terminal/console widget;
    # the Tape is a structured component, never a raw log
    assert "<pre" not in html
    assert "<textarea" not in html
    assert "console.log" not in html


@pytest.mark.parametrize("page", PAGES)
def test_no_profit_language(page: str) -> None:
    html = _client().get(page).text.lower()
    for banned in ("profit", "earnings", "guaranteed", "get rich"):
        assert banned not in html, f"{banned!r} appears on {page}"


def test_floor_shows_sample_size_and_unproven_status() -> None:
    html = _client().get("/").text
    assert "SIMULATED" in html
    assert "unproven" in html
    assert re.search(r"n=\d+|low sample", html)  # sample size is always shown


def test_research_marks_a_failing_gate_and_low_sample() -> None:
    html = _client().get("/research").text
    assert "FAIL" in html
    assert "OUT-OF-SAMPLE" in html
