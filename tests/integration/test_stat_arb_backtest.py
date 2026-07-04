"""docs/14 sleeve D (v4): `DistancePairsAdapter` run through a real, audited
`Session` over a genuine interleaved multi-symbol bar stream -- not just
unit-level `on_market` calls -- proving the engine's multi-symbol extension
composes with a sleeve D strategy into a real, hash-chain-verified
backtest, exactly as already proven for sleeve C
(`test_cross_sectional_backtest.py`).
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
from lqe.models.adapters.stat_arb_adapter import DistancePairsAdapter
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer
from lqe.risk.model import RiskModel

START = datetime(2026, 1, 1, tzinfo=UTC)


def _merged_bars(n: int, drop_from: int) -> list[MarketEvent]:
    """ETH tracks flat throughout; BTC tracks flat alongside it until
    `drop_from`, then drops sharply and *stays* down -- a real distance-
    spread divergence the strategy should trade, with enough bars left
    afterward for the resulting order to actually fill."""
    bars = []
    for i in range(n):
        ts = START + timedelta(minutes=i)
        btc = Decimal("80.0") if i >= drop_from else Decimal("100.0")
        eth = Decimal("10.0")
        for symbol, price in ((("ETH-USDT"), eth), (("BTC-USDT"), btc)):
            bars.append(
                MarketEvent(
                    exchange="binance", symbol=symbol, timeframe="1m", ts_open=ts,
                    o=price, h=price + Decimal("0.5"), l=price - Decimal("0.5"), c=price,
                    v=100.0, source_version="test",
                )
            )
    return bars


def test_distance_pairs_strategy_goes_long_in_a_real_audited_backtest() -> None:
    bars = _merged_bars(15, drop_from=10)
    clock = ReplayClock([bar.ts_open for bar in bars])
    strategy = DistancePairsAdapter(
        symbol="BTC-USDT", name="stat_arb_distance_test", partner="ETH-USDT",
        window=10, entry_z=1.5, exit_z=0.3,
    )
    symbol: Symbol = "BTC-USDT"
    session = Session(
        engine=Engine(run_id="stat-arb-backtest", book="sandbox", clock=clock),
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
    # the sharp final-bar divergence must have actually opened a real
    # position, not just run without crashing.
    assert session.accounting.position_qty("BTC-USDT") > Decimal("0")
    # only BTC-USDT bars (half the merged stream) ever advance this
    # session's own equity curve -- foreign ETH-USDT bars are observed,
    # never booked.
    assert len(session.equity_curve) == 1 + 15
