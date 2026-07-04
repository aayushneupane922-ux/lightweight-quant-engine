"""`run_universe_backtest` (V5 M27 "Universe Core", docs/15): several
single-instrument sessions sharing one audit log, fed a synchronized
multi-symbol bar stream. Proves: (1) deterministic replay, (2) a missing
bar for one symbol doesn't affect the others, (3) a cross-sectional
model -- permanently inert on the old fake synthetic universe -- actually
fires signals now that it observes real sibling-symbol bars.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.universe_runner import run_universe_backtest
from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol
from lqe.models.adapters.cross_sectional_adapter import CrossSectionalAdapter
from lqe.models.plugins.trend_ma_cross import TrendMaCross
from lqe.risk.model import RiskModel
from lqe.risk.rules import RiskConfig

BTC: Symbol = "BTC-USDT"
ETH: Symbol = "ETH-USDT"
SOL: Symbol = "SOL-USDT"
SYMBOLS = [BTC, ETH, SOL]
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: Symbol, minute: int, price: float) -> MarketEvent:
    p = Decimal(str(price))
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=NOW + timedelta(minutes=minute), o=p, h=p, l=p, c=p,
        v=1.0, source_version="test",
    )


def _universe_bars(n: int, *, drop_sol_at: set[int] = frozenset()) -> list[MarketEvent]:
    bars = []
    for i in range(n):
        bars.append(_bar(BTC, i, 100 + i * 2))  # strong uptrend
        bars.append(_bar(ETH, i, 100))  # flat
        if i not in drop_sol_at:
            bars.append(_bar(SOL, i, 100 - i))  # declining
    bars.sort(key=lambda b: b.ts_open)
    return bars


def _strategies() -> dict[Symbol, object]:
    return {
        BTC: CrossSectionalAdapter(
            symbol=BTC, name="xsec_btc", universe=SYMBOLS, lookback=5,
            top_quantile=0.34, metric="momentum",
        ),
        ETH: TrendMaCross(symbol=ETH, fast=3, slow=8),
        SOL: TrendMaCross(symbol=SOL, fast=3, slow=8),
    }


def test_cross_sectional_model_actually_fires_on_a_real_universe() -> None:
    # Previously permanently inert: catalog_scale.py fed these models a
    # fake 3-value synthetic price path with no live per-bar feed at all.
    bars = _universe_bars(20)
    result = run_universe_backtest(
        run_id="universe-xsec", symbols=SYMBOLS, bars=bars,
        strategies=_strategies(), starting_cash=Decimal("10000"),
    )
    signals = [e for e in result.engine.audit.records if e.type == "SignalEvent"]
    btc_signals = [e for e in signals if e.payload["strategy"] == "xsec_btc"]
    assert btc_signals, "the cross-sectional model never fired a signal"
    assert any(s.payload["direction"] == "LONG" for s in btc_signals)


def test_universe_backtest_is_deterministic_on_replay() -> None:
    bars = _universe_bars(15)
    result_a = run_universe_backtest(
        run_id="universe-det", symbols=SYMBOLS, bars=bars,
        strategies=_strategies(), starting_cash=Decimal("10000"),
    )
    result_b = run_universe_backtest(
        run_id="universe-det", symbols=SYMBOLS, bars=bars,
        strategies=_strategies(), starting_cash=Decimal("10000"),
    )
    assert result_a.engine.audit.verify() is True
    assert result_b.engine.audit.verify() is True
    assert result_a.engine.audit.head_hash == result_b.engine.audit.head_hash


def test_a_missing_symbol_does_not_crash_or_desync_the_others() -> None:
    bars = _universe_bars(15, drop_sol_at={5, 6, 7})
    result = run_universe_backtest(
        run_id="universe-missing", symbols=SYMBOLS, bars=bars,
        strategies=_strategies(), starting_cash=Decimal("10000"),
    )
    assert result.engine.audit.verify() is True
    missing = result.missing_counts()
    assert missing[SOL] == 3
    assert missing[BTC] == 0
    assert missing[ETH] == 0
    # BTC and ETH sessions still traded normally across the whole run.
    market_events = [e for e in result.engine.audit.records if e.type == "MarketEvent"]
    btc_bars_seen = [e for e in market_events if e.payload["symbol"] == BTC]
    assert len(btc_bars_seen) == 15


class _AlwaysBuy:
    """Test-only strategy: signals ENTER on every bar, regardless of
    existing position -- guarantees repeated fills across cycles so a
    cross-book aggregate has time to accumulate and (if a cap is tight
    enough) actually get hit, unlike a strategy that only ever enters once."""

    name = "always_buy"
    params: dict[str, object] = {}

    def __init__(self, *, symbol: Symbol) -> None:
        self._symbol = symbol

    def on_start(self, ctx: Context) -> None:
        return None

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction="LONG", strength=1.0,
                intent_kind="ENTER", bar_ts=ev.ts_open, reason="always buy",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None


def test_cross_book_sleeve_concentration_actually_engages() -> None:
    # V5 M27: all 3 books buy every bar in the same sleeve -- each book
    # alone stays under its own local per-strategy-budget, but a tight
    # portfolio-wide sleeve cap should still clamp/reject once the OTHER
    # books' notional (not just this book's own) eats the shared budget.
    bars = _universe_bars(10)
    sleeve_of = dict.fromkeys(SYMBOLS, "trend_momentum")

    tight = run_universe_backtest(
        run_id="universe-sleeve-tight", symbols=SYMBOLS, bars=bars,
        strategies={sym: _AlwaysBuy(symbol=sym) for sym in SYMBOLS},
        starting_cash=Decimal("10000"),
        risk_models={sym: RiskModel(config=RiskConfig(max_sleeve_gross=Decimal("0.05")))
                     for sym in SYMBOLS},
        sleeve_of_symbol=sleeve_of,
    )
    tight_hits = [
        e for e in tight.engine.audit.records if e.type == "RiskDecision"
        and "sleeve_concentration" in e.payload.get("rule_hits", [])
    ]
    assert tight_hits, "a tight cross-book sleeve cap never actually engaged"

    permissive = run_universe_backtest(
        run_id="universe-sleeve-loose", symbols=SYMBOLS, bars=bars,
        strategies={sym: _AlwaysBuy(symbol=sym) for sym in SYMBOLS},
        starting_cash=Decimal("10000"), sleeve_of_symbol=sleeve_of,
    )
    permissive_hits = [
        e for e in permissive.engine.audit.records if e.type == "RiskDecision"
        and "sleeve_concentration" in e.payload.get("rule_hits", [])
    ]
    assert not permissive_hits, "the default (permissive) sleeve cap should never engage"


def test_strategies_must_cover_exactly_the_symbols_given() -> None:
    import pytest

    bars = _universe_bars(5)
    with pytest.raises(ValueError, match="exactly one entry"):
        run_universe_backtest(
            run_id="universe-mismatch", symbols=SYMBOLS, bars=bars,
            strategies={BTC: TrendMaCross(symbol=BTC, fast=3, slow=8)},
            starting_cash=Decimal("10000"),
        )
