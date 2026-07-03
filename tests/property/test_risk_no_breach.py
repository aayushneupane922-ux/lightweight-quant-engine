"""docs/10 M5: no intent sequence breaches limits. Hypothesis generates
random BUY/SELL sequences; every approved/clamped qty is applied to a
tracked ledger, and the position/cash/exposure invariants must hold after
*every single step*, not just at the end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from lqe.core.events import OrderIntent
from lqe.risk.model import RiskModel
from lqe.risk.rules import PortfolioState, RiskConfig

SYMBOL = "BTC-USDT"
NOW = datetime(2026, 1, 1, tzinfo=UTC)
PRICE = Decimal("100")

CONFIG = RiskConfig(
    max_pos_symbol=Decimal("50"),
    max_gross_exposure=Decimal("0.8"),
    max_orders_per_day=10_000,
    max_orders_per_min=10_000,
)


@given(
    sides=st.lists(st.sampled_from(["BUY", "SELL"]), min_size=1, max_size=40),
    qtys=st.lists(st.decimals(min_value="0.1", max_value="30", places=2), min_size=1, max_size=40),
)
@settings(max_examples=200)
def test_no_intent_sequence_breaches_limits(sides: list[str], qtys: list[Decimal]) -> None:
    n = min(len(sides), len(qtys))
    risk = RiskModel(config=CONFIG)
    cash = Decimal("10000")
    position_qty = Decimal("0")

    for i in range(n):
        side = sides[i]
        qty = qtys[i]
        equity = cash + position_qty * PRICE
        intent = OrderIntent(
            intent_id=f"intent-{i}", signal_ref=f"sig-{i}", strategy="prop-test", symbol=SYMBOL,
            side=side,  # type: ignore[arg-type]
            qty=qty, order_type="MARKET", idempotency_key=f"key-{i}",
            reason="property test",
        )
        state = PortfolioState(
            symbol=SYMBOL, equity=equity, cash=cash, peak_equity=Decimal("10000"),
            daily_pnl=equity - Decimal("10000"), position_qty=position_qty,
            reference_price=PRICE, last_data_ts=NOW, now_ts=NOW,
        )
        decision = risk.check(intent, state)
        if decision.verdict == "REJECT":
            continue

        approved_qty = decision.approved_qty
        if side == "BUY":
            position_qty += approved_qty
            cash -= approved_qty * PRICE
        else:
            sell_qty = min(approved_qty, position_qty)  # MVP: long-only, can't go short
            position_qty -= sell_qty
            cash += sell_qty * PRICE

        assert position_qty <= CONFIG.max_pos_symbol
        assert cash >= 0
        current_equity = cash + position_qty * PRICE
        if current_equity > 0:
            gross_exposure = position_qty * PRICE / current_equity
            assert gross_exposure <= CONFIG.max_gross_exposure + Decimal("0.0001")
