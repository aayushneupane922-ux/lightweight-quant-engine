"""docs/14 (v4) sleeves C/D: `Session` can now be fed a merged, multi-symbol
bar stream so a cross-sectional/basket strategy can see other symbols' bars
via `Context.universe_closes` -- but the risk/accounting/order pipeline
stays scoped to exactly the session's own `symbol`, unchanged from the
single-symbol case. This is the engine extension the v4 cross-sectional
sleeve needed; it must not weaken the existing single-symbol guarantees.
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
from lqe.risk.model import RiskModel

OWN_SYMBOL: Symbol = "BTC-USDT"
FOREIGN_SYMBOL: Symbol = "ETH-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


class _RecordingStrategy:
    """Records every `on_market` call's (event symbol, universe snapshot);
    optionally emits a signal on a specific triggering bar index so tests
    can check whether that signal actually reached the order pipeline."""

    name = "recording"
    params: dict[str, object] = {}

    def __init__(self, *, symbol: Symbol, fire_at_call_index: int | None = None) -> None:
        self._symbol = symbol
        self._fire_at_call_index = fire_at_call_index
        self.calls: list[tuple[Symbol, dict[Symbol, Decimal]]] = []
        self._call_count = 0

    def on_start(self, ctx: Context) -> None:
        self.calls.clear()
        self._call_count = 0

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        self.calls.append((ev.symbol, dict(ctx.universe_closes)))
        idx = self._call_count
        self._call_count += 1
        if idx == self._fire_at_call_index:
            return [
                SignalEvent(
                    strategy=self.name, symbol=self._symbol, direction="LONG", strength=1.0,
                    intent_kind="ENTER", bar_ts=ev.ts_open, reason="test-triggered",
                )
            ]
        return []

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None


def _bar(symbol: Symbol, i: int, price: float) -> MarketEvent:
    p = Decimal(str(price))
    return MarketEvent(
        exchange="binance", symbol=symbol, timeframe="1m",
        ts_open=START + timedelta(minutes=i),
        o=p, h=p + Decimal("1"), l=p - Decimal("1"), c=p, v=100.0, source_version="test",
    )


def _session(strategy: _RecordingStrategy, bars: list[MarketEvent]) -> Session:
    clock = ReplayClock([bar.ts_open for bar in bars])
    return Session(
        engine=Engine(run_id="multi-symbol-test", book="sandbox", clock=clock),
        broker=PaperBroker(),
        accounting=Accounting(starting_cash=Decimal("10000")),
        strategy=strategy,
        sizer=FixedFractionalSizer(fraction=Decimal("0.1")),
        fill_simulator=MarketOrderFillSimulator(
            slippage=FixedBpsSlippage(5.0), commission=BpsCommission(bps=10.0),
        ),
        risk_model=RiskModel(),
        symbol=OWN_SYMBOL,
    )


def test_on_market_is_called_for_every_symbols_bars_not_just_its_own() -> None:
    strategy = _RecordingStrategy(symbol=OWN_SYMBOL)
    bars = [
        _bar(OWN_SYMBOL, 0, 100.0),
        _bar(FOREIGN_SYMBOL, 1, 10.0),
        _bar(OWN_SYMBOL, 2, 101.0),
    ]
    session = _session(strategy, bars)
    session.run(bars)
    assert [symbol for symbol, _ in strategy.calls] == [OWN_SYMBOL, FOREIGN_SYMBOL, OWN_SYMBOL]


def test_universe_closes_accumulates_every_symbols_latest_price() -> None:
    strategy = _RecordingStrategy(symbol=OWN_SYMBOL)
    bars = [
        _bar(OWN_SYMBOL, 0, 100.0),
        _bar(FOREIGN_SYMBOL, 1, 10.0),
        _bar(OWN_SYMBOL, 2, 101.0),
    ]
    session = _session(strategy, bars)
    session.run(bars)
    # by the 3rd call (this session's own second bar), the snapshot should
    # carry both symbols' latest closes.
    _, universe_at_third_call = strategy.calls[2]
    assert universe_at_third_call == {OWN_SYMBOL: Decimal("101.0"), FOREIGN_SYMBOL: Decimal("10.0")}


def test_a_signal_emitted_on_a_foreign_bar_is_discarded_not_ordered() -> None:
    # fire_at_call_index=1 -> the strategy emits a signal on its *second*
    # on_market call, which (per the bar sequence below) is the foreign
    # ETH-USDT bar, not BTC-USDT.
    strategy = _RecordingStrategy(symbol=OWN_SYMBOL, fire_at_call_index=1)
    bars = [
        _bar(OWN_SYMBOL, 0, 100.0),
        _bar(FOREIGN_SYMBOL, 1, 10.0),
        _bar(OWN_SYMBOL, 2, 101.0),
    ]
    session = _session(strategy, bars)
    session.run(bars)
    assert session.broker.working_orders() == []
    assert session.accounting.position_qty(OWN_SYMBOL) == Decimal("0")


def test_a_signal_emitted_on_the_own_symbols_bar_still_reaches_the_order_book() -> None:
    # fire_at_call_index=2 -> the strategy's *third* on_market call, which
    # is its own (BTC-USDT) bar -- this signal must still flow through the
    # existing risk/order pipeline exactly as in the single-symbol case.
    strategy = _RecordingStrategy(symbol=OWN_SYMBOL, fire_at_call_index=2)
    bars = [
        _bar(OWN_SYMBOL, 0, 100.0),
        _bar(FOREIGN_SYMBOL, 1, 10.0),
        _bar(OWN_SYMBOL, 2, 101.0),
    ]
    session = _session(strategy, bars)
    session.run(bars)
    assert len(session.broker.working_orders()) == 1


def test_foreign_bars_do_not_advance_the_equity_curve_or_position_events() -> None:
    strategy = _RecordingStrategy(symbol=OWN_SYMBOL)
    bars = [
        _bar(OWN_SYMBOL, 0, 100.0),
        _bar(FOREIGN_SYMBOL, 1, 10.0),
        _bar(FOREIGN_SYMBOL, 2, 11.0),
        _bar(OWN_SYMBOL, 3, 101.0),
    ]
    session = _session(strategy, bars)
    session.run(bars)
    # starting equity mark + one append per *own*-symbol bar only (2), not
    # once per bar seen (4).
    assert len(session.equity_curve) == 1 + 2


def test_a_pure_single_symbol_stream_behaves_exactly_as_before() -> None:
    # regression guard: feeding only the session's own symbol (the
    # universal case before this engine extension) must produce an
    # unchanged, empty-until-now universe_closes shape and identical
    # equity-curve length to what a single-symbol session always did.
    strategy = _RecordingStrategy(symbol=OWN_SYMBOL)
    bars = [_bar(OWN_SYMBOL, i, 100.0 + i) for i in range(5)]
    session = _session(strategy, bars)
    session.run(bars)
    assert len(strategy.calls) == 5
    assert all(symbol == OWN_SYMBOL for symbol, _ in strategy.calls)
    assert len(session.equity_curve) == 1 + 5


def test_context_defaults_to_an_empty_universe_when_unspecified() -> None:
    ctx = Context(symbol=OWN_SYMBOL, position_qty=Decimal("0"))
    assert ctx.universe_closes == {}
