"""docs/11 §11.12 (property/hypothesis): accounting conservation. Over any
random long-only fill sequence, money is conserved exactly — cash tracks an
independent running ledger, equity is always cash + Σ(qty·mark), and a flat
book's equity is mark-independent. Complements the example-based unit tests
in tests/unit/test_accounting.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from lqe.core.events import FillEvent
from lqe.portfolio.accounting import Accounting

SYMBOL = "BTC-USDT"
NOW = datetime(2026, 1, 1, tzinfo=UTC)

_ops = st.lists(
    st.tuples(
        st.sampled_from(["BUY", "SELL"]),
        st.decimals(min_value="0.10", max_value="20", places=2),  # qty
        st.decimals(min_value="1", max_value="500", places=2),  # price
        st.decimals(min_value="0", max_value="2", places=2),  # fee
    ),
    min_size=1,
    max_size=50,
)


@given(ops=_ops)
@settings(max_examples=300)
def test_cash_and_equity_are_conserved_after_every_fill(
    ops: list[tuple[str, Decimal, Decimal, Decimal]],
) -> None:
    start = Decimal("1000000")
    acc = Accounting(starting_cash=start)
    expected_cash = start
    expected_qty = Decimal("0")

    for side, qty, px, fee in ops:
        if side == "SELL":
            qty = min(qty, expected_qty)  # long-only: never sell more than held
            if qty <= 0:
                continue
        fill = FillEvent(
            order_id="o", fill_ts=NOW, fill_px=px, fill_qty=qty, fee=fee,
            slippage_bps=0.0, partial=False,
        )
        acc.apply_fill(symbol=SYMBOL, side=side, fill=fill)  # type: ignore[arg-type]

        notional = qty * px
        if side == "BUY":
            expected_cash -= notional + fee
            expected_qty += qty
        else:
            expected_cash += notional - fee
            expected_qty -= qty

        # 1. cash matches an independently-computed ledger (arithmetic conserved)
        assert acc.cash == expected_cash
        # 2. position quantity matches (long-only: buys - sells, never negative)
        assert acc.position_qty(SYMBOL) == expected_qty
        assert expected_qty >= 0
        # 3. equity identity: equity == cash + qty * mark, for any mark
        mark = Decimal("123.45")
        assert acc.equity({SYMBOL: mark}) == acc.cash + expected_qty * mark
        # 4. a flat book's equity is independent of the mark price
        if expected_qty == 0:
            assert acc.equity({SYMBOL: Decimal("9999")}) == acc.cash
