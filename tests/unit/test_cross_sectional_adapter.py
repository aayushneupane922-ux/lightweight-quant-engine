"""docs/14 sleeve C (v4): `CrossSectionalAdapter` must actually rank a
universe and act only on relative standing -- not on its own price path in
isolation, which is what makes this a genuinely different return driver
from the single-instrument sleeves.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.adapters.cross_sectional_adapter import CrossSectionalAdapter

UNIVERSE: tuple[Symbol, ...] = ("BTC-USDT", "ETH-USDT", "SOL-USDT")
START = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: Symbol, i: int, price: float) -> MarketEvent:
    p = Decimal(str(price))
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=START + timedelta(minutes=i),
        o=p, h=p + Decimal("1"), l=p - Decimal("1"), c=p, v=100.0, source_version="test",
    )


def test_rejects_a_symbol_outside_its_own_universe() -> None:
    with pytest.raises(ValueError, match="own ranking universe"):
        CrossSectionalAdapter(
            symbol="DOGE-USDT", name="x", universe=UNIVERSE, lookback=5,
        )


def test_rejects_an_out_of_range_top_quantile() -> None:
    with pytest.raises(ValueError, match="top_quantile"):
        CrossSectionalAdapter(
            symbol="BTC-USDT", name="x", universe=UNIVERSE, lookback=5, top_quantile=1.5,
        )


def test_returns_no_signal_until_the_whole_universe_has_enough_history() -> None:
    adapter = CrossSectionalAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, lookback=5, metric="momentum",
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    # only BTC has bars so far -- ETH/SOL have zero history.
    signals = []
    for i in range(3):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0 + i), ctx))
    assert signals == []


def test_momentum_goes_long_when_its_own_symbol_is_the_top_performer() -> None:
    adapter = CrossSectionalAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, lookback=5,
        top_quantile=0.34, metric="momentum",  # top 1 of 3
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(7):
        # BTC rallies hard; ETH/SOL are flat -- BTC should end up the clear
        # cross-sectional momentum leader.
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0 + i * 5), ctx))
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, 10.0), ctx))
        signals.extend(adapter.on_market(_bar("SOL-USDT", i, 20.0), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"
    assert enters[0].symbol == "BTC-USDT"


def test_momentum_stays_flat_when_its_own_symbol_lags_the_universe() -> None:
    adapter = CrossSectionalAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, lookback=5,
        top_quantile=0.34, metric="momentum",
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(7):
        # BTC is flat/falling while ETH/SOL rally -- BTC is the laggard.
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0 - i), ctx))
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, 10.0 + i * 2), ctx))
        signals.extend(adapter.on_market(_bar("SOL-USDT", i, 20.0 + i * 2), ctx))
    assert [s for s in signals if s.intent_kind == "ENTER"] == []


def test_reversal_is_the_mirror_image_of_momentum() -> None:
    # the same "BTC lags" scenario that keeps momentum flat should flip
    # reversal LONG -- it bets on BTC's underperformance bouncing back.
    adapter = CrossSectionalAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, lookback=5,
        top_quantile=0.34, metric="reversal",
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(7):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0 - i), ctx))
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, 10.0 + i * 2), ctx))
        signals.extend(adapter.on_market(_bar("SOL-USDT", i, 20.0 + i * 2), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1 and enters[0].direction == "LONG"


def test_low_vol_favors_the_calmest_instrument() -> None:
    adapter = CrossSectionalAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, lookback=5,
        top_quantile=0.34, metric="low_vol",
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    signals = []
    for i in range(7):
        # BTC barely moves; ETH/SOL whipsaw hard.
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0 + (0.01 * i)), ctx))
        eth_price = 10.0 + (5.0 if i % 2 == 0 else -4.0)
        sol_price = 20.0 + (8.0 if i % 2 == 0 else -7.0)
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, eth_price), ctx))
        signals.extend(adapter.on_market(_bar("SOL-USDT", i, sol_price), ctx))
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1 and enters[0].symbol == "BTC-USDT"


def test_a_foreign_bar_never_emits_a_signal_for_this_adapters_own_symbol() -> None:
    adapter = CrossSectionalAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, lookback=2, metric="momentum",
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    result = adapter.on_market(_bar("ETH-USDT", 0, 10.0), ctx)
    assert result == []


def test_a_bar_outside_the_declared_universe_is_ignored() -> None:
    adapter = CrossSectionalAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, lookback=2, metric="momentum",
    )
    ctx = Context(symbol="BTC-USDT", position_qty=Decimal("0"))
    adapter.on_start(ctx)
    result = adapter.on_market(_bar("DOGE-USDT", 0, 1.0), ctx)
    assert result == []
    assert "DOGE-USDT" not in adapter._history  # noqa: SLF001 - internal state check


def test_on_fill_is_a_no_op() -> None:
    adapter = CrossSectionalAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, lookback=2, metric="momentum",
    )
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise
