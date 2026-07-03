"""docs/archive/19 §19.1 items 1 & 3: startup must assert `is_paper`, and
`PaperBroker` must be the only usable `ExecutionAdapter`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lqe.backtest.make_session import Session
from lqe.core.clock import ReplayClock
from lqe.core.engine import Engine
from lqe.core.errors import LockoutViolation
from lqe.execution.base import ExecutionAdapter
from lqe.execution.commission import BpsCommission
from lqe.execution.fills import MarketOrderFillSimulator
from lqe.execution.paper_broker import PaperBroker
from lqe.execution.slippage import FixedBpsSlippage
from lqe.models.plugins.trend_ma_cross import TrendMaCross
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer
from lqe.risk.model import RiskModel


def test_paper_broker_satisfies_the_execution_adapter_protocol() -> None:
    # mypy-checked structural conformance: if PaperBroker ever drifts from
    # the ExecutionAdapter shape, this assignment fails type-checking.
    adapter: ExecutionAdapter = PaperBroker()
    assert adapter.is_paper is True


class _NotPaper:
    is_paper = False

    def submit(self, order: object) -> None:
        raise AssertionError("must never be called")

    def cancel(self, order_id: str) -> None:
        raise AssertionError("must never be called")

    def working_orders(self) -> list[object]:
        return []


def test_session_refuses_a_non_paper_broker_at_construction() -> None:
    clock = ReplayClock([datetime(2026, 1, 1, tzinfo=UTC)])
    engine = Engine(run_id="lockout-test", book="sandbox", clock=clock)
    with pytest.raises(LockoutViolation):
        Session(
            engine=engine,
            broker=_NotPaper(),  # type: ignore[arg-type]
            accounting=Accounting(starting_cash=Decimal("10000")),
            strategy=TrendMaCross(symbol="BTC-USDT", fast=2, slow=3),
            sizer=FixedFractionalSizer(),
            fill_simulator=MarketOrderFillSimulator(
                slippage=FixedBpsSlippage(0.0), commission=BpsCommission(bps=0.0)
            ),
            risk_model=RiskModel(),
            symbol="BTC-USDT",
        )
