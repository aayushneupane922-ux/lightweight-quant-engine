"""`IndicatorRuleAdapter`'s generic ENTER/EXIT transition bookkeeping,
isolated from any specific preset via a fake target-state function.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import PRESETS, IndicatorRuleAdapter

SYMBOL: Symbol = "BTC-USDT"


def _bar(i: int, price: float = 100.0) -> MarketEvent:
    return MarketEvent(
        exchange="binance", symbol=SYMBOL, timeframe="1m",
        ts_open=datetime(2026, 1, 1, tzinfo=UTC), o=Decimal(str(price)), h=Decimal(str(price)),
        l=Decimal(str(price)), c=Decimal(str(price)), v=100.0, source_version="test",
    )


def test_unknown_preset_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown preset"):
        IndicatorRuleAdapter(symbol=SYMBOL, preset="not-a-real-preset", name="x", params={})


def test_every_registered_preset_constructs_and_ignores_other_symbols() -> None:
    for preset_name in PRESETS:
        adapter = IndicatorRuleAdapter(
            symbol=SYMBOL, preset=preset_name, name=preset_name, params={}
        )
        ctx = Context(symbol=SYMBOL, position_qty=Decimal("0"))
        adapter.on_start(ctx)
        other_symbol_bar = MarketEvent(
            exchange="binance", symbol="ETH-USDT", timeframe="1m",
            ts_open=datetime(2026, 1, 1, tzinfo=UTC), o=Decimal("1"), h=Decimal("1"),
            l=Decimal("1"), c=Decimal("1"), v=1.0, source_version="test",
        )
        assert adapter.on_market(other_symbol_bar, ctx) == []


def test_target_long_emits_a_single_enter_and_then_stays_silent() -> None:
    adapter = IndicatorRuleAdapter(symbol=SYMBOL, preset="tsmom", name="x", params={"lookback": 2})
    ctx = Context(symbol=SYMBOL, position_qty=Decimal("0"))
    adapter.on_start(ctx)

    # rising prices -> once enough history exists, tsmom's target flips to LONG
    signals = []
    for i, price in enumerate([100.0, 101.0, 102.0, 103.0]):
        signals.extend(adapter.on_market(_bar(i, price), ctx))

    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"
    # once LONG, a further rising bar shouldn't re-emit another ENTER
    more = adapter.on_market(_bar(4, 104.0), ctx)
    assert more == []


def test_on_start_seeds_position_from_context() -> None:
    adapter = IndicatorRuleAdapter(symbol=SYMBOL, preset="tsmom", name="x", params={"lookback": 2})
    ctx = Context(symbol=SYMBOL, position_qty=Decimal("5"))
    adapter.on_start(ctx)
    assert adapter._position == "LONG"  # noqa: SLF001 - verifying internal state seeding


def test_on_fill_is_a_no_op() -> None:
    adapter = IndicatorRuleAdapter(symbol=SYMBOL, preset="tsmom", name="x", params={"lookback": 2})
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise
