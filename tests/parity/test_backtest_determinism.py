"""End-to-end backtest determinism (docs/10 M3): two runs of the same
config+bars+seed produce identical audit hash chains and identical
decisions (orders/fills), not just identical hashes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.plugins.trend_ma_cross import TrendMaCross

SYMBOL: Symbol = "BTC-USDT"


def _bars(n: int) -> list[MarketEvent]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        # a simple oscillation so the MA cross actually fires more than once
        price = price + (Decimal("5") if (i // 10) % 2 == 0 else Decimal("-5"))
        bars.append(
            MarketEvent(
                exchange="binance",
                symbol=SYMBOL,
                timeframe="1m",
                ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                o=price,
                h=price + Decimal("1"),
                l=price - Decimal("1"),
                c=price,
                v=100.0,
                source_version="test",
            )
        )
    return bars


def _run() -> tuple[list[str], list[dict[str, object]]]:
    bars = _bars(80)
    strategy = TrendMaCross(symbol=SYMBOL, fast=5, slow=20)
    session = run_backtest(
        run_id="determinism-test",
        symbol=SYMBOL,
        bars=bars,
        strategy=strategy,
        starting_cash=Decimal("10000"),
    )
    hashes = [record.hash for record in session.engine.audit.records]
    orders = [record.payload for record in session.engine.audit.records if record.type == "Order"]
    return hashes, orders


def test_backtest_hash_chain_is_deterministic_across_runs() -> None:
    hashes_a, _ = _run()
    hashes_b, _ = _run()
    assert hashes_a == hashes_b
    assert len(hashes_a) > 0


def test_backtest_decisions_are_reproducible() -> None:
    _, orders_a = _run()
    _, orders_b = _run()
    assert orders_a == orders_b
    assert len(orders_a) > 0  # the oscillating price series must trigger at least one trade
