"""The scaled catalog (docs/10 M11, docs/03 §3.1/§3.6): 50+ models reached
by config, honestly gated — native models admit and run deterministically,
heavy-lib models quarantine transparently when the optional extra is
absent, and nothing is ever ranked `validated` without a gate PASS.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.catalog_scale import build_scaled_catalog

SYMBOL: Symbol = "BTC-USDT"


def _bars(n: int = 200) -> list[MarketEvent]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        price = price + Decimal("1") if (i // 12) % 2 == 0 else price - Decimal("1")
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    return bars


def test_at_least_fifty_models_are_available() -> None:
    _, results = build_scaled_catalog(SYMBOL)
    assert len(results) >= 50
    assert len({r.model_id for r in results}) == len(results)  # no duplicate ids


def test_native_models_admit_and_span_four_families() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    admitted = catalog.all()
    assert len(admitted) >= 40
    families = {e.manifest.family for e in admitted}
    assert families >= {"trend", "momentum", "mean_reversion", "volatility"}


def test_every_admitted_model_is_unproven_until_gated() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    # honesty: breadth does not confer validation — the gate does
    assert all(e.manifest.status == "unproven" for e in catalog.all())


def test_heavy_lib_models_quarantine_transparently_when_absent() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    quarantined = catalog.quarantined()
    assert quarantined, "heavy-lib models should quarantine without the 'models' extra"
    # transparent: each carries a real reason, never silently dropped
    for record in quarantined:
        assert record.reasons
        assert "models" in record.reasons[0]  # the pip install '.[models]' hint


def test_the_deliberately_weak_control_is_present() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    assert any(e.manifest.id == "naive_always_long" for e in catalog.all())


def test_admitted_models_run_a_deterministic_backtest() -> None:
    catalog, _ = build_scaled_catalog(SYMBOL)
    bars = _bars()
    # sample a few admitted models across families; each must run and be
    # bit-reproducible (same audit head hash on a second run)
    sample = catalog.all()[:6]
    for entry in sample:
        a = run_backtest(
            run_id=f"scale:{entry.manifest.id}:a", symbol=SYMBOL, bars=bars,
            strategy=entry.strategy_factory(), starting_cash=Decimal("10000"),
        )
        b = run_backtest(
            run_id=f"scale:{entry.manifest.id}:a", symbol=SYMBOL, bars=bars,
            strategy=entry.strategy_factory(), starting_cash=Decimal("10000"),
        )
        assert a.engine.audit.verify()
        assert a.engine.audit.head_hash == b.engine.audit.head_hash
