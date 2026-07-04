"""docs/14 sleeve F (v4) M24 exit gate: "carry/basis models run on real
funding data" -- the full loop, not just a hardcoded synthetic side-channel.
Fetch (fake ccxt exchange, same shape a real one returns) -> validate ->
curated Parquet -> catalog version -> read back -> feed into
`FundingCarryAdapter` -> a real, hash-chain-verified backtest. Distinct
from `test_funding_carry_backtest.py`, which uses the catalog's built-in
synthetic side-channel for out-of-the-box registration/demo purposes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from lqe.backtest.make_session import Session
from lqe.core.clock import ReplayClock
from lqe.core.engine import Engine
from lqe.core.events import MarketEvent
from lqe.data.funding_adapter import CcxtFundingRateAdapter
from lqe.data.ingest import ingest_funding_rates
from lqe.execution.commission import BpsCommission
from lqe.execution.fills import MarketOrderFillSimulator
from lqe.execution.paper_broker import PaperBroker
from lqe.execution.slippage import FixedBpsSlippage
from lqe.models.adapters.funding_carry_adapter import FundingCarryAdapter
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer
from lqe.risk.model import RiskModel
from lqe.storage.catalog import Catalog
from lqe.storage.parquet_funding import read_funding_rates

EXCHANGE = "binance"
SYMBOL = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeExchange:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def fetch_funding_rate_history(
        self, native_symbol: str, since: int | None = None
    ) -> list[dict[str, object]]:
        return self._rows


def _funding_row(hour: int, rate: float) -> dict[str, object]:
    ts = START + timedelta(hours=hour)
    return {"timestamp": int(ts.timestamp() * 1000), "fundingRate": rate}


def _bar(i: int, price: float) -> MarketEvent:
    p = Decimal(str(price))
    ts = START + timedelta(minutes=i)
    return MarketEvent(
        exchange=EXCHANGE, symbol=SYMBOL, timeframe="1m", ts_open=ts,
        o=p, h=p + Decimal("0.5"), l=p - Decimal("0.5"), c=p, v=100.0, source_version="test",
    )


def test_funding_carry_strategy_trades_on_ingested_real_funding_data(tmp_path: Path) -> None:
    # a rising funding rate, settled every 8h -- clears the entry threshold
    # partway through the backtest window.
    rows = [_funding_row(h, 0.0001 + 0.00005 * h) for h in range(0, 24, 8)]
    adapter = CcxtFundingRateAdapter(EXCHANGE, exchange=_FakeExchange(rows))
    root = tmp_path / "data"
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        ingest_result = ingest_funding_rates(
            adapter, exchange=EXCHANGE, symbol=SYMBOL, root=root, catalog=catalog,
        )
    assert ingest_result.report.passed is True

    # read back exactly the way a real backtest/live entry point would --
    # not the hardcoded synthetic side-channel `catalog_scale.py` uses.
    curated = read_funding_rates(
        root / "curated" / "funding", exchange=EXCHANGE, symbol=SYMBOL,
    )
    funding_history = [(rate.ts, rate.rate) for rate in curated]
    assert len(funding_history) == 3

    bars = [_bar(i, 100.0) for i in range(1500)]  # spans past the last funding settlement
    clock = ReplayClock([bar.ts_open for bar in bars])
    strategy = FundingCarryAdapter(
        symbol=SYMBOL, name="carry_from_real_data", funding_history=funding_history,
        entry_rate=0.00015, exit_rate=0.0001,
    )
    session = Session(
        engine=Engine(run_id="funding-carry-real-data", book="sandbox", clock=clock),
        broker=PaperBroker(),
        accounting=Accounting(starting_cash=Decimal("10000")),
        strategy=strategy,
        sizer=FixedFractionalSizer(fraction=Decimal("0.1")),
        fill_simulator=MarketOrderFillSimulator(
            slippage=FixedBpsSlippage(5.0), commission=BpsCommission(bps=10.0),
        ),
        risk_model=RiskModel(),
        symbol=SYMBOL,
    )
    session.run(bars)

    assert session.engine.audit.verify()
    assert session.accounting.position_qty(SYMBOL) > Decimal("0")
