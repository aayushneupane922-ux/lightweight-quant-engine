"""docs/14 sleeve C (v4): `CrossSectionalAdapter` run through a real,
audited `Session` over a genuine interleaved multi-symbol bar stream --
not just unit-level `on_market` calls -- proving the engine's multi-symbol
extension (docs/14 v4, `Context.universe_closes`) and the adapter actually
compose into a real, hash-chain-verified backtest.
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
from lqe.models.adapters.cross_sectional_adapter import CrossSectionalAdapter
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer
from lqe.risk.model import RiskModel

UNIVERSE: tuple[Symbol, ...] = ("BTC-USDT", "ETH-USDT", "SOL-USDT")
START = datetime(2026, 1, 1, tzinfo=UTC)


def _merged_bars(n: int) -> list[MarketEvent]:
    """One bar per symbol per minute, interleaved in timestamp order --
    BTC trends up hard, ETH/SOL stay flat, so BTC should end up the clear
    cross-sectional momentum leader for most of the run."""
    bars = []
    for i in range(n):
        ts = START + timedelta(minutes=i)
        btc = Decimal(str(100.0 + i * 3))
        eth = Decimal("10.0")
        sol = Decimal("20.0")
        for symbol, price in ((("BTC-USDT"), btc), (("ETH-USDT"), eth), (("SOL-USDT"), sol)):
            bars.append(
                MarketEvent(
                    exchange="binance", symbol=symbol, timeframe="1m", ts_open=ts,
                    o=price, h=price + Decimal("0.5"), l=price - Decimal("0.5"), c=price,
                    v=100.0, source_version="test",
                )
            )
    return bars


def test_cross_sectional_strategy_goes_long_its_own_symbol_in_a_real_audited_backtest() -> None:
    bars = _merged_bars(30)
    clock = ReplayClock([bar.ts_open for bar in bars])
    strategy = CrossSectionalAdapter(
        symbol="BTC-USDT", name="xsec_momentum_test", universe=UNIVERSE,
        lookback=5, top_quantile=0.34, metric="momentum",
    )
    session = Session(
        engine=Engine(run_id="xsec-backtest", book="sandbox", clock=clock),
        broker=PaperBroker(),
        accounting=Accounting(starting_cash=Decimal("10000")),
        strategy=strategy,
        sizer=FixedFractionalSizer(fraction=Decimal("0.1")),
        fill_simulator=MarketOrderFillSimulator(
            slippage=FixedBpsSlippage(5.0), commission=BpsCommission(bps=10.0),
        ),
        risk_model=RiskModel(),
        symbol="BTC-USDT",
    )
    session.run(bars)

    assert session.engine.audit.verify()
    # BTC is the runaway cross-sectional winner here -- the strategy must
    # have actually entered a real position, not just run without crashing.
    assert session.accounting.position_qty("BTC-USDT") > Decimal("0")
    # only BTC-USDT bars (1/3 of the merged stream) ever advance this
    # session's own equity curve -- foreign ETH/SOL bars are observed, not
    # booked, exactly as the engine extension promises.
    assert len(session.equity_curve) == 1 + 30
