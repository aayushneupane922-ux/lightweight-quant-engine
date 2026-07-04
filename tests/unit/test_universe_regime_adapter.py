"""docs/15 V5 M28 ("Wake the Sleeves"): `UniverseRegimeGateAdapter` must
actually gate its own-symbol trend entry on the universe's average pairwise
return correlation -- not just on its own price path -- which is what makes
this a genuinely universe-wide regime overlay, distinct from this catalog's
other (single-instrument) regime models.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from lqe.core.context import Context
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.adapters.universe_regime_adapter import UniverseRegimeGateAdapter

UNIVERSE: tuple[Symbol, ...] = ("BTC-USDT", "ETH-USDT", "SOL-USDT")
START = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: Symbol, i: int, price: float) -> MarketEvent:
    p = Decimal(str(round(price, 6)))
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=START + timedelta(minutes=i),
        o=p, h=p + Decimal("1"), l=p - Decimal("1"), c=p, v=100.0, source_version="test",
    )


def _ctx() -> Context:
    return Context(symbol="BTC-USDT", position_qty=Decimal("0"))


def test_rejects_a_symbol_outside_its_own_universe() -> None:
    with pytest.raises(ValueError, match="own regime universe"):
        UniverseRegimeGateAdapter(symbol="DOGE-USDT", name="x", universe=UNIVERSE)


def test_rejects_a_universe_with_fewer_than_two_other_symbols() -> None:
    with pytest.raises(ValueError, match="at least 2 other"):
        UniverseRegimeGateAdapter(
            symbol="BTC-USDT", name="x", universe=("BTC-USDT", "ETH-USDT"),
        )


def test_rejects_an_out_of_range_corr_threshold() -> None:
    with pytest.raises(ValueError, match="corr_threshold"):
        UniverseRegimeGateAdapter(
            symbol="BTC-USDT", name="x", universe=UNIVERSE, corr_threshold=1.5,
        )


def test_returns_no_signal_until_the_whole_universe_has_enough_history() -> None:
    adapter = UniverseRegimeGateAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, corr_lookback=5, trend_lookback=5,
    )
    ctx = _ctx()
    adapter.on_start(ctx)
    # only BTC has bars so far -- ETH/SOL have zero history.
    signals = []
    for i in range(3):
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, 100.0 + i), ctx))
    assert signals == []


def _drive_idiosyncratic(adapter: UniverseRegimeGateAdapter, n: int = 10) -> list:
    ctx = _ctx()
    adapter.on_start(ctx)
    signals = []
    btc_price = 100.0
    for i in range(n):
        # BTC climbs steadily (constant %, zero return-variance -- its own
        # correlation with anything is the adapter's explicit zero-variance
        # guard); ETH/SOL alternate in exact opposite phase, so they're
        # strongly *anti*-correlated with each other. Average pairwise
        # correlation across the universe stays comfortably below any
        # reasonable threshold -- an idiosyncratic regime.
        signals.extend(adapter.on_market(_bar("BTC-USDT", i, btc_price), ctx))
        btc_price *= 1.01
        eth_price = 10.0 + (3.0 if i % 2 == 0 else -3.0)
        sol_price = 20.0 + (-3.0 if i % 2 == 0 else 3.0)
        signals.extend(adapter.on_market(_bar("ETH-USDT", i, eth_price), ctx))
        signals.extend(adapter.on_market(_bar("SOL-USDT", i, sol_price), ctx))
    return signals


def _drive_systemic(adapter: UniverseRegimeGateAdapter, n: int = 10) -> list:
    ctx = _ctx()
    adapter.on_start(ctx)
    signals = []
    # every symbol follows the exact same relative move sequence (just a
    # different base price) -- their return series are identical, so every
    # pairwise correlation is exactly 1.0: a systemic/risk-off regime.
    multipliers = [1.0, 1.05, 0.98, 1.03, 0.99, 1.04, 1.01, 1.06, 1.0, 1.05]
    bases = {"BTC-USDT": 100.0, "ETH-USDT": 10.0, "SOL-USDT": 20.0}
    running = dict(bases)
    for i in range(n):
        for sym, base in bases.items():
            running[sym] = base * multipliers[i % len(multipliers)]
            signals.extend(adapter.on_market(_bar(sym, i, running[sym]), ctx))
    return signals


def test_goes_long_when_idiosyncratic_regime_and_its_own_symbol_uptrends() -> None:
    adapter = UniverseRegimeGateAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, corr_lookback=5,
        corr_threshold=0.5, trend_lookback=5,
    )
    signals = _drive_idiosyncratic(adapter)
    enters = [s for s in signals if s.intent_kind == "ENTER"]
    assert len(enters) == 1
    assert enters[0].direction == "LONG"
    assert enters[0].symbol == "BTC-USDT"


def test_stays_flat_in_a_systemic_regime_even_though_its_own_symbol_uptrends() -> None:
    adapter = UniverseRegimeGateAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, corr_lookback=5,
        corr_threshold=0.5, trend_lookback=5,
    )
    signals = _drive_systemic(adapter)
    assert [s for s in signals if s.intent_kind == "ENTER"] == []


def test_a_foreign_bar_never_emits_a_signal_for_this_adapters_own_symbol() -> None:
    adapter = UniverseRegimeGateAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, corr_lookback=2, trend_lookback=2,
    )
    ctx = _ctx()
    adapter.on_start(ctx)
    result = adapter.on_market(_bar("ETH-USDT", 0, 10.0), ctx)
    assert result == []


def test_a_bar_outside_the_declared_universe_is_ignored() -> None:
    adapter = UniverseRegimeGateAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, corr_lookback=2, trend_lookback=2,
    )
    ctx = _ctx()
    adapter.on_start(ctx)
    result = adapter.on_market(_bar("DOGE-USDT", 0, 1.0), ctx)
    assert result == []
    assert "DOGE-USDT" not in adapter._history  # noqa: SLF001 - internal state check


def test_on_fill_is_a_no_op() -> None:
    adapter = UniverseRegimeGateAdapter(
        symbol="BTC-USDT", name="x", universe=UNIVERSE, corr_lookback=2, trend_lookback=2,
    )
    adapter.on_fill(None, None)  # type: ignore[arg-type]  # must not raise
