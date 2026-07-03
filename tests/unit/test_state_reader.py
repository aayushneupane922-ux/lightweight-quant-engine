"""`StateReader` reconstructs UI state read-only from an audit log
(docs/11 §11.9): honesty fields always present, per-model state/return/
sample size derived by replaying events, structured tape rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.plugins.trend_ma_cross import TrendMaCross
from lqe.storage.state_reader import CatalogModelInfo, StateReader

SYMBOL: Symbol = "BTC-USDT"


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


def _reader() -> StateReader:
    session = run_backtest(
        run_id="sr-test", symbol=SYMBOL, bars=_bars(120),
        strategy=TrendMaCross(symbol=SYMBOL, fast=5, slow=20), starting_cash=Decimal("10000"),
    )
    return StateReader(
        session.engine.audit.records,
        catalog=[CatalogModelInfo(model_id="trend_ma_cross", family="trend", status="unproven")],
    )


def test_snapshot_always_reports_simulated_true() -> None:
    snap = _reader().snapshot()
    assert snap.simulated is True


def test_snapshot_carries_session_stats_from_the_last_risk_state() -> None:
    snap = _reader().snapshot()
    assert snap.session is not None
    assert snap.session.equity > 0
    assert snap.session.drawdown >= 0.0


def test_model_cell_carries_sample_size_and_status() -> None:
    snap = _reader().snapshot()
    cell = next(c for c in snap.models if c.model_id == "trend_ma_cross")
    assert cell.family == "trend"
    assert cell.status == "unproven"  # never "validated" without a gate PASS
    assert cell.n_trades > 0
    assert cell.sim_return_pct is not None


def test_a_catalog_model_that_never_traded_shows_no_return_and_zero_trades() -> None:
    session = run_backtest(
        run_id="sr-empty", symbol=SYMBOL, bars=_bars(120),
        strategy=TrendMaCross(symbol=SYMBOL, fast=5, slow=20), starting_cash=Decimal("10000"),
    )
    reader = StateReader(
        session.engine.audit.records,
        catalog=[
            CatalogModelInfo(model_id="trend_ma_cross", family="trend"),
            CatalogModelInfo(model_id="never_ran", family="momentum"),
        ],
    )
    snap = reader.snapshot()
    idle = next(c for c in snap.models if c.model_id == "never_ran")
    assert idle.n_trades == 0
    assert idle.sim_return_pct is None  # rendered "—", not a fake 0.0
    assert idle.state == "ARMED"


def test_tape_is_incremental_and_capped() -> None:
    reader = _reader()
    everything = reader.tape(after_seq=0, limit=100000)
    assert everything, "expected a non-empty tape"
    highest = everything[-1].seq
    # nothing strictly after the last seq
    assert reader.tape(after_seq=highest) == []
    # the limit keeps only the most-recent rows
    assert len(reader.tape(after_seq=0, limit=3)) == 3


def test_data_health_reports_bars_seen_per_symbol() -> None:
    snap = _reader().snapshot()
    health = next(h for h in snap.data_health if h.symbol == SYMBOL)
    assert health.bars_seen == 120
    assert health.last_bar is not None
