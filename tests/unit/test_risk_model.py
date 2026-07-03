"""Focused tests for RiskModel.check/on_bar beyond the property test."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


def test_approve_when_within_all_limits() -> None:
    risk = RiskModel()
    decision = risk.check(_buy("1"), _state())
    assert decision.verdict == "APPROVE"
    assert decision.approved_qty == Decimal("1")
    assert decision.rule_hits == []


def test_clamp_when_cash_insufficient() -> None:
    risk = RiskModel()
    decision = risk.check(_buy("1000"), _state(cash=Decimal("500")))
    assert decision.verdict == "CLAMP"
    assert decision.approved_qty == Decimal("5")
    assert "cash_sufficiency" in decision.rule_hits


def test_reject_non_whitelisted_symbol() -> None:
    risk = RiskModel(config=RiskConfig(symbol_whitelist=frozenset({"ETH-USDT"})))
    decision = risk.check(_buy("1"), _state())
    assert decision.verdict == "REJECT"
    assert "symbol_whitelist" in decision.rule_hits


def test_reject_stale_data() -> None:
    risk = RiskModel(config=RiskConfig(max_staleness=timedelta(minutes=1)))
    decision = risk.check(_buy("1"), _state(last_data_ts=NOW - timedelta(hours=1)))
    assert decision.verdict == "REJECT"
    assert "stale_data" in decision.rule_hits


def test_reject_duplicate_signal() -> None:
    risk = RiskModel()
    decision = risk.check(_buy("1"), _state(recent_intent_keys=frozenset({"k1"})))
    assert decision.verdict == "REJECT"
    assert "duplicate_signal" in decision.rule_hits


def test_clamp_at_max_position() -> None:
    risk = RiskModel(config=RiskConfig(max_pos_symbol=Decimal("10")))
    decision = risk.check(_buy("5"), _state(position_qty=Decimal("8")))
    assert decision.verdict == "CLAMP"
    assert decision.approved_qty == Decimal("2")


def test_on_bar_auto_kills_on_max_drawdown_breach() -> None:
    risk = RiskModel(config=RiskConfig(max_dd=Decimal("0.1")))
    state = _state(peak_equity=Decimal("10000"), equity=Decimal("8000"))  # 20% dd
    event = risk.on_bar(state)
    assert risk.kill_active is True
    assert "max_drawdown" in event.breaches
    assert event.kill_active is True


def test_on_bar_auto_kills_on_daily_loss_breach() -> None:
    risk = RiskModel(config=RiskConfig(max_daily_loss=Decimal("500")))
    state = _state(daily_pnl=Decimal("-600"))
    event = risk.on_bar(state)
    assert risk.kill_active is True
    assert "max_daily_loss" in event.breaches


def test_on_bar_no_breach_stays_unkilled() -> None:
    risk = RiskModel()
    event = risk.on_bar(_state())
    assert risk.kill_active is False
    assert event.breaches == []
