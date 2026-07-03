"""`StaticWeightProjectionAdapter` bookkeeping (docs/03 §3.3, portfolio/
risk_allocation families) — isolated from any real optimizer library via a
fake `weight_fn`, since none of skfolio/PyPortfolioOpt/riskfolio-lib are
required just to prove the ENTER/EXIT projection logic is correct.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.adapters._portfolio_projection import StaticWeightProjectionAdapter

SYMBOL: Symbol = "BTC-USDT"
OTHER: Symbol = "ETH-USDT"


def _bar(symbol: Symbol = SYMBOL) -> MarketEvent:
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=datetime(2026, 1, 1, tzinfo=UTC), o=Decimal("1"), h=Decimal("1"),
        l=Decimal("1"), c=Decimal("1"), v=1.0, source_version="test",
    )


def test_symbol_must_be_in_the_universe() -> None:
    with pytest.raises(ValueError, match="universe_closes"):
        StaticWeightProjectionAdapter(
            symbol=SYMBOL, name="x", universe_closes={OTHER: [1.0, 2.0]},
            weight_fn=lambda u: {OTHER: 1.0},
        )


def test_positive_weight_above_threshold_goes_long_once() -> None:
    adapter = StaticWeightProjectionAdapter(
        symbol=SYMBOL, name="x",
        universe_closes={SYMBOL: [1.0, 2.0], OTHER: [1.0, 1.0]},
        weight_fn=lambda u: {SYMBOL: 0.6, OTHER: 0.4}, min_weight=0.1,
    )
    ctx = Context(symbol=SYMBOL, position_qty=Decimal("0"))
    adapter.on_start(ctx)

    signals = adapter.on_market(_bar(), ctx)
    assert len(signals) == 1
    assert signals[0].direction == "LONG"
    assert signals[0].intent_kind == "ENTER"

    # a second bar shouldn't re-emit anything: it's a static, one-shot projection
    assert adapter.on_market(_bar(), ctx) == []


def test_weight_below_threshold_stays_flat_and_emits_nothing() -> None:
    adapter = StaticWeightProjectionAdapter(
        symbol=SYMBOL, name="x", universe_closes={SYMBOL: [1.0], OTHER: [1.0]},
        weight_fn=lambda u: {SYMBOL: 0.0, OTHER: 1.0}, min_weight=0.1,
    )
    ctx = Context(symbol=SYMBOL, position_qty=Decimal("0"))
    adapter.on_start(ctx)
    assert adapter.on_market(_bar(), ctx) == []


def test_ignores_bars_for_other_symbols() -> None:
    adapter = StaticWeightProjectionAdapter(
        symbol=SYMBOL, name="x", universe_closes={SYMBOL: [1.0], OTHER: [1.0]},
        weight_fn=lambda u: {SYMBOL: 1.0}, min_weight=0.1,
    )
    ctx = Context(symbol=SYMBOL, position_qty=Decimal("0"))
    adapter.on_start(ctx)
    assert adapter.on_market(_bar(OTHER), ctx) == []
