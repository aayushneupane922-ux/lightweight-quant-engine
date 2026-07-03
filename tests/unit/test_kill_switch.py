"""docs/10 M5: kill => no risk-increasing order until a human clears it
(docs/archive/14 §14.5): persisted, survives restart, never auto-clears.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from lqe.core.events import OrderIntent
from lqe.risk.kill_switch import KillSwitch
from lqe.risk.model import RiskModel
from lqe.risk.rules import PortfolioState

SYMBOL = "BTC-USDT"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _intent(side: str, qty: str) -> OrderIntent:
    return OrderIntent(
        intent_id=f"i-{side}", signal_ref="s1", strategy="test", symbol=SYMBOL, side=side,  # type: ignore[arg-type]
        qty=Decimal(qty), order_type="MARKET", idempotency_key=f"k-{side}", reason="test",
    )


def _state(position_qty: Decimal = Decimal("5")) -> PortfolioState:
    return PortfolioState(
        symbol=SYMBOL, equity=Decimal("10000"), cash=Decimal("9500"), peak_equity=Decimal("10000"),
        daily_pnl=Decimal("0"), position_qty=position_qty, reference_price=Decimal("100"),
        last_data_ts=NOW, now_ts=NOW,
    )


def test_kill_rejects_a_buy_but_allows_a_flattening_sell() -> None:
    risk = RiskModel()
    risk.kill(reason="manual test kill")

    buy_decision = risk.check(_intent("BUY", "1"), _state())
    assert buy_decision.verdict == "REJECT"
    assert "kill_switch_active" in buy_decision.rule_hits

    sell_decision = risk.check(_intent("SELL", "3"), _state(position_qty=Decimal("5")))
    assert sell_decision.verdict == "APPROVE"


def test_kill_persists_until_explicitly_cleared() -> None:
    risk = RiskModel()
    risk.kill(reason="test")
    assert risk.kill_active is True
    assert risk.check(_intent("BUY", "1"), _state()).verdict == "REJECT"
    assert risk.check(_intent("BUY", "1"), _state()).verdict == "REJECT"

    risk.clear_kill(operator="alice")
    assert risk.kill_active is False
    assert risk.check(_intent("BUY", "1"), _state()).verdict != "REJECT"


def test_clear_requires_a_named_operator() -> None:
    risk = RiskModel()
    risk.kill(reason="test")
    with pytest.raises(ValueError):
        risk.clear_kill(operator="")


def test_kill_switch_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "kill.json"
    KillSwitch(path).trigger(reason="disk persistence test")

    # simulate a process restart: a fresh KillSwitch pointed at the same file
    reloaded = KillSwitch(path)
    assert reloaded.active is True
    assert reloaded.reason == "disk persistence test"


def test_kill_switch_never_auto_clears_on_reload(tmp_path: Path) -> None:
    path = tmp_path / "kill.json"
    KillSwitch(path).trigger(reason="test")
    for _ in range(3):
        assert KillSwitch(path).active is True


def test_clear_persists_across_reload(tmp_path: Path) -> None:
    path = tmp_path / "kill.json"
    switch = KillSwitch(path)
    switch.trigger(reason="test")
    switch.clear(operator="bob")

    reloaded = KillSwitch(path)
    assert reloaded.active is False
