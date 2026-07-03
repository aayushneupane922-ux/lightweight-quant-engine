"""A fill may only ever use the bar strictly *after* the one that produced
the order (docs/archive/08 §8.2 bar-timing rule; docs/10 M3's "fills never
use future data" test). Proven with a strategy that fires on the very first
bar, so the fill is forced onto the second bar's open — easy to hand-check.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.make_session import Session
from lqe.core.clock import ReplayClock
from lqe.core.context import Context
from lqe.core.engine import Engine
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol
from lqe.execution.commission import BpsCommission
from lqe.execution.fills import MarketOrderFillSimulator
from lqe.execution.paper_broker import PaperBroker
from lqe.execution.slippage import FixedBpsSlippage
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer


class _FireOnFirstBar:
    """Test-only strategy: emits one ENTER signal on the first bar it sees,
    then never signals again."""

    name = "fire_on_first_bar"
    params: dict[str, object] = {}

    def __init__(self, symbol: Symbol) -> None:
        self._symbol = symbol
        self._fired = False

    def on_start(self, ctx: Context) -> None:
        self._fired = False

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if self._fired or ev.symbol != self._symbol:
            return []
        self._fired = True
        return [
            SignalEvent(
                strategy=self.name,
                symbol=self._symbol,
                direction="LONG",
                strength=1.0,
                intent_kind="ENTER",
                bar_ts=ev.ts_open,
                reason="test fixture: always fire on the first bar",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None


def _bar(offset_minutes: int, o: str, c: str) -> MarketEvent:
    return MarketEvent(
        exchange="binance",
        symbol="BTC-USDT",
        timeframe="1m",
        ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=offset_minutes),
        o=Decimal(o),
        h=Decimal(o) + Decimal("1"),
        l=Decimal(o) - Decimal("1"),
        c=Decimal(c),
        v=100.0,
        source_version="test",
    )


def test_fill_uses_the_next_bars_open_not_the_signal_bars_own_data() -> None:
    bars = [
        _bar(0, "100", "105"),  # signal fires here (close=105) — must NOT be used for the fill
        _bar(1, "200", "201"),  # the fill must use THIS bar's open (200), not bar 0's close/open
        _bar(2, "300", "301"),
    ]
    symbol: Symbol = "BTC-USDT"
    strategy = _FireOnFirstBar(symbol)
    clock = ReplayClock([b.ts_open for b in bars])
    engine = Engine(run_id="lookahead-test", book="sandbox", clock=clock)
    broker = PaperBroker()
    accounting = Accounting(starting_cash=Decimal("100000"))
    session = Session(
        engine=engine,
        broker=broker,
        accounting=accounting,
        strategy=strategy,
        sizer=FixedFractionalSizer(fraction=Decimal("0.1")),
        fill_simulator=MarketOrderFillSimulator(
            slippage=FixedBpsSlippage(0.0), commission=BpsCommission(bps=0.0)
        ),
        symbol=symbol,
    )

    session.run(bars)

    fill_events = [
        env.payload for env in engine.audit.records if env.type == "FillEvent"
    ]
    assert len(fill_events) == 1
    # zero slippage/commission configured, so fill_px must equal bar[1]'s raw open (200) —
    # never bar[0]'s open (100) or close (105), which is what a look-ahead bug would use.
    assert Decimal(fill_events[0]["fill_px"]) == Decimal("200")
