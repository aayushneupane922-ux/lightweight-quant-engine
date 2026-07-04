"""docs/14 sleeve D (v4): `JohansenBasketAdapter` must estimate a genuine
basket cointegrating relationship (not just a single fixed hedge ratio, as
`StatsmodelsPairsAdapter` does) and trade its combination's z-score -- a
different formulation from the native distance/lead-lag/basket-arb
adapters in `stat_arb_adapter.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.adapters.johansen_adapter import JohansenBasketAdapter

START = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: Symbol, i: int, price: float) -> MarketEvent:
    p = Decimal(str(price))
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=START + timedelta(minutes=i),
        o=p, h=p + Decimal("1"), l=p - Decimal("1"), c=p, v=100.0, source_version="test",
    )


def test_rejects_symbol_inside_its_own_basket() -> None:
    with pytest.raises(ValueError, match="own basket"):
        JohansenBasketAdapter(symbol="BTC-USDT", name="x", basket=("BTC-USDT", "ETH-USDT"))


def test_rejects_an_empty_basket() -> None:
    with pytest.raises(ValueError, match="at least one"):
        JohansenBasketAdapter(symbol="BTC-USDT", name="x", basket=())


def test_no_signal_until_window_is_full() -> None:
    adapter = JohansenBasketAdapter(
        symbol="BTC-USDT", name="x", basket=("ETH-USDT", "SOL-USDT"), window=30,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(10):
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, 10.0 + i * 0.1), ctx))
        signals.extend(adapter.on_market(_bar("SOL-USDT", i, 20.0 + i * 0.1), ctx))
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0 + i * 0.1), ctx))
    assert signals == []


def test_goes_long_when_the_basket_combination_diverges_cheap() -> None:
    # a basket cointegrated by construction (BTC drives ETH/SOL plus small
    # noise), with a sharp late divergence in BTC alone -- deterministic
    # seed chosen so the Johansen-estimated combination's z-score clears
    # entry_z exactly once.
    rng = np.random.default_rng(0)
    n = 40
    btc = 100 + np.cumsum(rng.normal(0, 0.3, n))
    eth = 0.5 * btc + rng.normal(0, 0.1, n) + 50
    sol = 0.3 * btc + rng.normal(0, 0.1, n) + 20
    btc_shocked = btc.copy()
    btc_shocked[-1] -= 15

    adapter = JohansenBasketAdapter(
        symbol="BTC-USDT", name="x", basket=("ETH-USDT", "SOL-USDT"),
        window=30, entry_z=1.5, exit_z=0.3,
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(n):
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, float(eth[i])), ctx))
        signals.extend(adapter.on_market(_bar("SOL-USDT", i, float(sol[i])), ctx))
        price = float(btc_shocked[i]) if i == n - 1 else float(btc[i])
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, price), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"
    assert enters[0].symbol == "BTC-USDT"


def test_a_bar_outside_the_basket_is_ignored() -> None:
    adapter = JohansenBasketAdapter(
        symbol="BTC-USDT", name="x", basket=("ETH-USDT", "SOL-USDT"),
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    result = adapter.on_market(_bar("DOGE-USDT", 0, 1.0), ctx)
    assert result == []


def test_on_fill_is_a_no_op() -> None:
    adapter = JohansenBasketAdapter(
        symbol="BTC-USDT", name="x", basket=("ETH-USDT", "SOL-USDT"),
    )
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise
