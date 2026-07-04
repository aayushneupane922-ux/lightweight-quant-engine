"""docs/03 §3.4/§3.7 + docs/10 M6: every default-catalog model must pass
intake and complete a real Research backtest — not just construct.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.registry import build_default_catalog

SYMBOL: Symbol = "BTC-USDT"


def _bars(n: int) -> list[MarketEvent]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        # a gentle trend with a wobble so every family (trend, momentum,
        # mean-reversion, volatility) sees something non-degenerate.
        step = Decimal("1") if (i // 15) % 2 == 0 else Decimal("-1")
        wobble = Decimal("2") if i % 5 == 0 else Decimal("0")
        price = price + step + wobble - (wobble / 2 if i % 5 == 0 else Decimal("0"))
        bars.append(
            MarketEvent(
                exchange="binance", symbol=SYMBOL, timeframe="1m",
                ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                o=price, h=price + Decimal("1"), l=price - Decimal("1"), c=price,
                v=100.0, source_version="test",
            )
        )
    return bars


def test_default_catalog_has_at_least_ten_models_across_four_families() -> None:
    catalog, results = build_default_catalog(SYMBOL)
    assert all(r.passed for r in results), [r for r in results if not r.passed]
    assert len(catalog.all()) >= 10
    families = {e.manifest.family for e in catalog.all()}
    assert families >= {"trend", "momentum", "mean_reversion", "volatility"}
    assert catalog.quarantined() == []


def test_every_default_catalog_model_carries_a_sleeve_tag() -> None:
    # docs/14 §3 (v4): every model needs a sleeve tag for the diversification
    # score to be computable, including the pre-v4 default catalog.
    catalog, _ = build_default_catalog(SYMBOL)
    for entry in catalog.all():
        assert entry.manifest.sleeve, f"{entry.manifest.id} has no sleeve tag"


def test_every_default_catalog_model_completes_a_real_backtest() -> None:
    catalog, _ = build_default_catalog(SYMBOL)
    bars = _bars(300)
    for entry in catalog.all():
        session = run_backtest(
            run_id=f"catalog-check:{entry.manifest.id}",
            symbol=SYMBOL,
            bars=bars,
            strategy=entry.strategy_factory(),
            starting_cash=Decimal("10000"),
        )
        # equity_curve includes the starting point, so it's bars + 1 long
        assert len(session.equity_curve) == len(bars) + 1
        assert session.engine.audit.verify()
