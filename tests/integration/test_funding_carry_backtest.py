"""docs/14 sleeve F (v4): `BasisCarryAdapter` run through a real, audited
`Session` over a genuine interleaved spot+perp bar stream -- proving the
engine's multi-symbol extension composes with a sleeve F strategy into a
real, hash-chain-verified backtest, exactly as already proven for sleeves
C and D.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.make_session import Session
from lqe.core.clock import ReplayClock
from lqe.core.engine import Engine
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.execution.commission import BpsCommission
from lqe.execution.fills import MarketOrderFillSimulator
from lqe.execution.paper_broker import PaperBroker
from lqe.execution.slippage import FixedBpsSlippage
from lqe.models.adapters.basis_carry_adapter import BasisCarryAdapter
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer
from lqe.risk.model import RiskModel

START = datetime(2026, 1, 1, tzinfo=UTC)


def _merged_bars(n: int, premium_from: int) -> list[MarketEvent]:
    """Spot stays flat; perp trades at a rich, sustained premium starting
    at `premium_from` -- a real, held basis divergence with enough bars
    left afterward for the resulting order to actually fill."""
    bars = []
    for i in range(n):
        ts = START + timedelta(minutes=i)
        spot = Decimal("100.0")
        perp = Decimal("103.0") if i >= premium_from else Decimal("100.05")
        for symbol, price in ((("BTC-USDT-PERP"), perp), (("BTC-USDT"), spot)):
            bars.append(
                MarketEvent(
                    exchange="synthetic", symbol=symbol, timeframe="1m", ts_open=ts,
                    o=price, h=price + Decimal("0.5"), l=price - Decimal("0.5"), c=price,
                    v=100.0, source_version="test",
                )
            )
    return bars


def test_basis_carry_strategy_goes_long_in_a_real_audited_backtest() -> None:
    bars = _merged_bars(15, premium_from=10)
    clock = ReplayClock([bar.ts_open for bar in bars])
    strategy = BasisCarryAdapter(
        symbol="BTC-USDT", name="basis_carry_test", perp_symbol="BTC-USDT-PERP",
        entry_basis=0.01, exit_basis=0.0,
    )
    symbol: Symbol = "BTC-USDT"
    session = Session(
        engine=Engine(run_id="funding-carry-backtest", book="sandbox", clock=clock),
        broker=PaperBroker(),
        accounting=Accounting(starting_cash=Decimal("10000")),
        strategy=strategy,
        sizer=FixedFractionalSizer(fraction=Decimal("0.1")),
        fill_simulator=MarketOrderFillSimulator(
            slippage=FixedBpsSlippage(5.0), commission=BpsCommission(bps=10.0),
        ),
        risk_model=RiskModel(),
        symbol=symbol,
    )
    session.run(bars)

    assert session.engine.audit.verify()
    # the sustained perp premium must have actually opened a real position.
    assert session.accounting.position_qty("BTC-USDT") > Decimal("0")
    # only BTC-USDT bars (half the merged stream) ever advance this
    # session's own equity curve -- foreign perp bars are observed, never
    # booked.
    assert len(session.equity_curve) == 1 + 15
