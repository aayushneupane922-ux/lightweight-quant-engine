"""`StateReader.reconciliation()` (V5 M27 Universe Core): a model_id that
genuinely trades more than one symbol must get one row per symbol, never
a silently conflated combined position -- the bug this milestone found
and fixed in `_Reconstruction._strategies_by_symbol`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from lqe.core.engine import AuditLog
from lqe.core.events import FillEvent, Order, OrderIntent
from lqe.core.types import Symbol
from lqe.storage.state_reader import StateReader

BTC: Symbol = "BTC-USDT"
ETH: Symbol = "ETH-USDT"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _same_strategy_two_symbols_log() -> AuditLog:
    """A single strategy name ("alpha") that trades BTC and ETH, each with
    a distinct net position -- BTC net long 3, ETH net long 1 (after a
    partial exit)."""
    log = AuditLog()
    seq = 1

    def _fill(symbol: Symbol, intent_id: str, side: str, qty: str, px: str) -> None:
        nonlocal seq
        order_id = f"order:{intent_id}"
        log.append(
            event_type="OrderIntent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
            payload=OrderIntent(
                intent_id=intent_id, signal_ref=f"s-{intent_id}", strategy="alpha",
                symbol=symbol, side=side, qty=Decimal(qty), order_type="MARKET",
                idempotency_key=f"k-{intent_id}", reason="test",
            ),
        )
        seq += 1
        log.append(
            event_type="Order", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
            payload=Order(
                order_id=order_id, intent_ref=intent_id, side=side, qty=Decimal(qty),
                order_type="MARKET", status="PENDING",
            ),
        )
        seq += 1
        log.append(
            event_type="FillEvent", run_id="r", seq=seq, book="sandbox", sim_ts=NOW,
            payload=FillEvent(
                order_id=order_id, fill_ts=NOW, fill_px=Decimal(px), fill_qty=Decimal(qty),
                fee=Decimal("0.01"), slippage_bps=0.5, partial=False,
            ),
        )
        seq += 1

    _fill(BTC, "btc-1", "BUY", "5", "100")
    _fill(BTC, "btc-2", "SELL", "2", "110")  # BTC net -> 3
    _fill(ETH, "eth-1", "BUY", "1", "10")  # ETH net -> 1
    return log


def test_a_model_trading_two_symbols_gets_two_separate_reconciliation_rows() -> None:
    reader = StateReader(_same_strategy_two_symbols_log().records)
    rows = reader.reconciliation()
    by_symbol = {row.symbol: row for row in rows}

    assert set(by_symbol) == {BTC, ETH}
    assert all(row.model_id == "alpha" for row in rows)

    btc_row = by_symbol[BTC]
    assert btc_row.net_qty == Decimal("3")
    assert btc_row.n_trades == 2

    eth_row = by_symbol[ETH]
    assert eth_row.net_qty == Decimal("1")
    assert eth_row.n_trades == 1

    # the historical bug: without symbol-keying, BTC's 3 and ETH's 1 would
    # have been silently summed into a single conflated "alpha" row.
    assert btc_row.net_qty != btc_row.net_qty + eth_row.net_qty
