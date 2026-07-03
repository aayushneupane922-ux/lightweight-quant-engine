from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lqe.core.events import FillEvent
from lqe.portfolio.accounting import Accounting

TS = datetime(2026, 1, 1, tzinfo=UTC)


def _fill(px: str, qty: str, fee: str) -> FillEvent:
    return FillEvent(
        order_id="o1",
        fill_ts=TS,
        fill_px=Decimal(px),
        fill_qty=Decimal(qty),
        fee=Decimal(fee),
        slippage_bps=5.0,
        partial=False,
    )


def test_buy_reduces_cash_and_opens_position() -> None:
    acc = Accounting(starting_cash=Decimal("10000"))
    acc.apply_fill(symbol="BTC-USDT", side="BUY", fill=_fill("100", "10", "1"))

    assert acc.cash == Decimal("10000") - Decimal("1000") - Decimal("1")
    assert acc.position_qty("BTC-USDT") == Decimal("10")
    assert acc.equity({"BTC-USDT": Decimal("100")}) == acc.cash + Decimal("1000")


def test_round_trip_buy_then_sell_flat_conserves_money() -> None:
    acc = Accounting(starting_cash=Decimal("10000"))
    acc.apply_fill(symbol="BTC-USDT", side="BUY", fill=_fill("100", "10", "1"))
    acc.apply_fill(symbol="BTC-USDT", side="SELL", fill=_fill("100", "10", "1"))

    # same price in and out: net change is exactly the two fees
    assert acc.cash == Decimal("10000") - Decimal("2")
    assert acc.position_qty("BTC-USDT") == Decimal("0")
    # flat position: equity is cash alone, regardless of the mark price
    assert acc.equity({"BTC-USDT": Decimal("999")}) == acc.cash


def test_sell_at_a_profit_realizes_pnl() -> None:
    acc = Accounting(starting_cash=Decimal("10000"))
    acc.apply_fill(symbol="BTC-USDT", side="BUY", fill=_fill("100", "10", "0"))
    acc.apply_fill(symbol="BTC-USDT", side="SELL", fill=_fill("110", "10", "0"))

    assert acc.position_state("BTC-USDT").realized_pnl == Decimal("100")  # (110-100)*10
    assert acc.cash == Decimal("10000") + Decimal("100")


def test_equity_marks_open_position_at_given_price() -> None:
    acc = Accounting(starting_cash=Decimal("10000"))
    acc.apply_fill(symbol="BTC-USDT", side="BUY", fill=_fill("100", "10", "0"))

    # equity = cash + qty * mark, for any mark price supplied
    assert acc.equity({"BTC-USDT": Decimal("150")}) == acc.cash + Decimal("10") * Decimal("150")


def test_selling_more_than_held_raises() -> None:
    acc = Accounting(starting_cash=Decimal("10000"))
    acc.apply_fill(symbol="BTC-USDT", side="BUY", fill=_fill("100", "5", "0"))
    with pytest.raises(ValueError):
        acc.apply_fill(symbol="BTC-USDT", side="SELL", fill=_fill("100", "10", "0"))
