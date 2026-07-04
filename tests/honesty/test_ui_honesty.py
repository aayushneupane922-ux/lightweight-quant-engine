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
PAGES = ["/", "/catalog", "/research", "/risk", "/daily", "/blotter", "/intel"]


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


# --- M22: honesty coverage for the M18-M21 surfaces ---------------------


def _client_with_autopilot() -> TestClient:
    from lqe.autonomy.optimizer import OptunaOptimizer
    from lqe.autonomy.orchestrator import Orchestrator
    from lqe.autonomy.promotion_gate import GateThresholds, PromotionGate
    from lqe.autonomy.searchable import default_searchable_models
    from lqe.autonomy.validator import Validator

    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    price = Decimal("100")
    for i in range(220):
        price = price + Decimal("1") if (i // 11) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=start + timedelta(minutes=i),
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
    orch.run(steps=2, start=start)
    data = DeskData(state_reader=StateReader(orch.engine.audit.records), control=ControlPlane())
    return TestClient(create_app(data))


def test_blotter_carries_its_own_simulated_tag_and_read_only_narration() -> None:
    html = _client().get("/blotter").text
    assert "SIMULATED" in html
    assert "constructs no order" in html.lower()


def test_intel_carries_observe_only_tag_and_gate_language() -> None:
    html = _client().get("/intel").text
    assert "OBSERVE-ONLY" in html
    assert "cannot" in html.lower() or "can neither" in html.lower()


def test_blotter_shows_a_reason_when_empty_not_a_blank_panel() -> None:
    html = _client().get("/blotter").text
    assert 'id="blotter-empty"' in html
    # the honest-empty-state helper always returns a non-empty reason string
    assert re.search(r'id="blotter-empty"[^>]*>[^<]*\S', html)


def test_conversation_feed_shows_a_reason_when_empty_not_a_blank_panel() -> None:
    html = _client().get("/intel").text
    assert "No autonomy steps recorded yet" in html


@pytest.mark.filterwarnings("ignore")
def test_conversation_feed_renders_no_cryptic_ids_in_the_default_view() -> None:
    # tests/unit/test_state_reader.py already proves ConversationMessage.text
    # never carries raw IDs; this pins the same guarantee one layer up, at
    # the actual rendered Jinja HTML for a real campaign, since a template
    # change could leak `hypo_id`/`candidate_id`/`trial_id` into the default
    # (always-visible) view even if the underlying message text stays clean.
    # The Judge's raw `evidence` dict is deliberately exempt -- it's the
    # power-user disclosure behind <details>, per the M21 spec's own "no
    # code/JSON/cryptic IDs in the default view, Details for power users".
    html = _client_with_autopilot().get("/intel").text
    assert '<div class="convo"' in html  # the feed actually rendered content
    visible = re.sub(r"<details>.*?</details>", "", html, flags=re.DOTALL)
    for banned in ("hypo_id", "candidate_id", "trial_id", "cand:", "hypo:"):
        assert banned not in visible, f"{banned!r} leaked into the default conversation view"


@pytest.mark.filterwarnings("ignore")
def test_conversation_feed_carries_no_raw_json_blob() -> None:
    html = _client_with_autopilot().get("/intel").text
    # the Judge's evidence is rendered as plain "k: v" lines inside <details>,
    # never as a raw dict/JSON dump
    assert "{'" not in html and '{"' not in html
