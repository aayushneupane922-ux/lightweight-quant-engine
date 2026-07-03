"""Multi-instrument (basket) accounting reconciliation (docs/10 M11).
One shared cash pool funds every instrument; an independent replay of the
whole basket's fills must match cash and every per-symbol position, and a
mismatch halts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lqe.core.errors import ReconciliationError
from lqe.core.events import FillEvent
from lqe.portfolio.accounting import Accounting
from lqe.risk.reconciliation import BasketFillRecord, reconcile_basket

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _fill(qty: str, px: str, fee: str = "1") -> FillEvent:
    return FillEvent(
        order_id="o", fill_ts=NOW, fill_px=Decimal(px), fill_qty=Decimal(qty),
        fee=Decimal(fee), slippage_bps=0.0, partial=False,
    )


def _basket() -> list[BasketFillRecord]:
    return [
        ("BTC-USDT", "BUY", _fill("1", "100")),
        ("ETH-USDT", "BUY", _fill("10", "10")),
        ("BTC-USDT", "SELL", _fill("1", "110")),  # close BTC at a profit
        ("ETH-USDT", "BUY", _fill("5", "12")),
    ]


def test_basket_reconciles_across_symbols() -> None:
    fills = _basket()
    live = Accounting(starting_cash=Decimal("10000"))
    for symbol, side, fill in fills:
        live.apply_fill(symbol=symbol, side=side, fill=fill)
    # independent replay must match cash + every position
    reconcile_basket(live=live, starting_cash=Decimal("10000"), fills=fills)  # must not raise
    assert live.position_qty("BTC-USDT") == Decimal("0")
    assert live.position_qty("ETH-USDT") == Decimal("15")


def test_basket_position_mismatch_halts() -> None:
    fills = _basket()
    live = Accounting(starting_cash=Decimal("10000"))
    for symbol, side, fill in fills:
        live.apply_fill(symbol=symbol, side=side, fill=fill)
    # corrupt only the ETH position (cash left intact) so the per-symbol
    # position check — not the cash check — is what trips
    live.position_state("ETH-USDT").qty += Decimal("3")
    with pytest.raises(ReconciliationError, match="ETH-USDT"):
        reconcile_basket(live=live, starting_cash=Decimal("10000"), fills=fills)


def test_basket_cash_mismatch_halts() -> None:
    fills = _basket()
    live = Accounting(starting_cash=Decimal("9999"))  # wrong starting cash
    for symbol, side, fill in fills:
        live.apply_fill(symbol=symbol, side=side, fill=fill)
    with pytest.raises(ReconciliationError, match="cash"):
        reconcile_basket(live=live, starting_cash=Decimal("10000"), fills=fills)
