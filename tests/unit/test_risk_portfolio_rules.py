"""`check_portfolio_gross_exposure`/`check_sleeve_concentration` (V5 M27
Universe Core): both are no-ops in the ordinary single-book case
(`portfolio_equity`/etc. `None`), and both correctly REJECT/CLAMP once a
multi-instrument orchestrator populates the cross-book fields.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from lqe.core.events import OrderIntent
from lqe.risk.model import RiskModel
from lqe.risk.rules import PortfolioState, RiskConfig

SYMBOL = "BTC-USDT"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _buy(qty: str) -> OrderIntent:
    return OrderIntent(
        intent_id="i1", signal_ref="s1", strategy="t", symbol=SYMBOL, side="BUY",
        qty=Decimal(qty), order_type="MARKET", idempotency_key="k1", reason="t",
    )


def _state(**overrides: Any) -> PortfolioState:
    base: dict[str, Any] = {
        "symbol": SYMBOL, "equity": Decimal("10000"), "cash": Decimal("10000"),
        "peak_equity": Decimal("10000"), "daily_pnl": Decimal("0"), "position_qty": Decimal("0"),
        "reference_price": Decimal("100"), "last_data_ts": NOW, "now_ts": NOW,
    }
    base.update(overrides)
    return PortfolioState(**base)


def test_portfolio_gross_exposure_is_a_noop_without_cross_book_fields() -> None:
    risk = RiskModel(config=RiskConfig(max_gross_exposure=Decimal("0.1")))
    decision = risk.check(_buy("1"), _state())  # portfolio_equity/notional both None
    assert decision.verdict == "APPROVE"
    assert "portfolio_gross_exposure" not in decision.rule_hits


def test_portfolio_gross_exposure_clamps_using_room_left_across_all_books() -> None:
    # This book alone is flat, but the OTHER books already use $8000 of a
    # 90%-of-$10000 = $9000 cap -- only $1000 of room left for anyone.
    risk = RiskModel(config=RiskConfig(max_gross_exposure=Decimal("0.9")))
    decision = risk.check(
        _buy("50"),  # 50 * 100 = 5000 notional, way over the 1000 of room left
        _state(portfolio_equity=Decimal("10000"), portfolio_gross_notional=Decimal("8000")),
    )
    assert decision.verdict == "CLAMP"
    assert "portfolio_gross_exposure" in decision.rule_hits
    assert decision.approved_qty == Decimal("10")  # 1000 of room / 100 price


def test_portfolio_gross_exposure_rejects_outright_when_cap_already_exhausted() -> None:
    risk = RiskModel(config=RiskConfig(max_gross_exposure=Decimal("0.5")))
    decision = risk.check(
        _buy("1"),
        _state(portfolio_equity=Decimal("10000"), portfolio_gross_notional=Decimal("5000")),
    )
    assert decision.verdict == "REJECT"
    assert "portfolio_gross_exposure" in decision.rule_hits


def test_sleeve_concentration_is_a_noop_without_cross_book_fields() -> None:
    risk = RiskModel(config=RiskConfig(max_sleeve_gross=Decimal("0.1")))
    decision = risk.check(_buy("1"), _state())  # sleeve_notional_used is None
    assert decision.verdict == "APPROVE"
    assert "sleeve_concentration" not in decision.rule_hits


def test_sleeve_concentration_blocks_a_third_book_in_an_already_full_sleeve() -> None:
    # Two sibling books already parked $4500 of a $5000 sleeve cap (10000 *
    # 0.5) -- this book (same sleeve, itself flat) barely has room left.
    risk = RiskModel(config=RiskConfig(max_sleeve_gross=Decimal("0.5")))
    decision = risk.check(
        _buy("20"),  # 20*100 = 2000 notional, way over the 500 of room left
        _state(portfolio_equity=Decimal("10000"), sleeve_notional_used=Decimal("4500")),
    )
    assert decision.verdict == "CLAMP"
    assert "sleeve_concentration" in decision.rule_hits
    assert decision.approved_qty == Decimal("5")  # 500 / 100


def test_sleeve_concentration_rejects_outright_when_sleeve_cap_exhausted() -> None:
    risk = RiskModel(config=RiskConfig(max_sleeve_gross=Decimal("0.5")))
    decision = risk.check(
        _buy("1"),
        _state(portfolio_equity=Decimal("10000"), sleeve_notional_used=Decimal("5000")),
    )
    assert decision.verdict == "REJECT"
    assert "sleeve_concentration" in decision.rule_hits
