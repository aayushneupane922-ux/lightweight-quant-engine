"""`LiveMultiModelRunner`/`build_fleet` (post-v1.0 extension, V5 M27 live
follow-up): every model gets its own fully independent paper book, all
sharing one hash-chained engine and one kill switch. Two trivial, fully
deterministic fake strategies (not real catalog indicators) make the
fleet-level arithmetic and attribution easy to verify exactly, rather than
depending on real indicator signal timing.

Since the M27 live follow-up, `process_bar` no longer ticks/emits the
`MarketEvent` itself (mirroring `backtest.make_session.Session._on_bar`) --
the caller (a `LiveSession` orchestrating N runners sharing one `Engine`, or
here, the test loop itself) must `engine.tick()` + `engine.emit(...)` once
per bar before calling `process_bar`. See `_drive`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.core.clock import ManualClock
from lqe.core.context import Context
from lqe.core.engine import Engine
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.live.multi_model_runner import LiveMultiModelRunner, build_fleet
from lqe.models.catalog import CatalogEntry
from lqe.models.manifest import DataNeeds, ModelManifest
from lqe.risk.kill_switch import KillSwitch
from lqe.risk.model import RiskModel
from lqe.risk.portfolio_context import PortfolioContext

SYMBOL = "BTC-USDT"
OTHER_SYMBOL = "ETH-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _drive(engine: Engine, runner: LiveMultiModelRunner, bars: list[MarketEvent]) -> None:
    """The caller-side contract `process_bar` now expects: tick the clock,
    emit the bar's `MarketEvent`, THEN hand it to the runner -- exactly the
    loop `run_universe_backtest` already uses for `Session._on_bar`."""
    clock = engine.clock
    for bar in bars:
        clock.set(bar.ts_open)  # type: ignore[attr-defined]
        engine.tick()
        engine.emit("MarketEvent", bar)
        runner.process_bar(bar)


def _manifest(model_id: str) -> ModelManifest:
    return ModelManifest(
        id=model_id, family="trend", sleeve="trend_momentum", one_liner="test fixture",
        economic_rationale="n/a - test fixture only",
        data_needs=DataNeeds(instruments=1, kind="OHLCV"), oss_libs=["own"],
        params_schema={}, failure_modes=["n/a"],
    )


class AlwaysLong:
    """Enters LONG once on the first bar, then holds forever."""

    name = "always_long"
    params: dict[str, object] = {}

    def __init__(self) -> None:
        self._entered = False

    def on_start(self, ctx: Context) -> None:
        self._entered = False

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if self._entered:
            return []
        self._entered = True
        return [
            SignalEvent(
                strategy=self.name, symbol=ev.symbol, direction="LONG", strength=1.0,
                intent_kind="ENTER", bar_ts=ev.ts_open, reason="always enter once",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        pass


class NeverTrades:
    """Never signals -- a control to prove one model's activity doesn't
    leak into another's book."""

    name = "never_trades"
    params: dict[str, object] = {}

    def on_start(self, ctx: Context) -> None:
        pass

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        return []

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        pass


def _bars(n: int, *, start_price: Decimal = Decimal("100")) -> list[MarketEvent]:
    bars = []
    price = start_price
    for i in range(n):
        ts = START + timedelta(minutes=i)
        bars.append(
            MarketEvent(
                exchange="fake", symbol=SYMBOL, timeframe="1m", ts_open=ts,
                o=price, h=price + 1, l=price - 1, c=price, v=1.0, source_version="fake:1",
            )
        )
        price += Decimal("1")
    return bars


def _fleet_entries() -> list[CatalogEntry]:
    return [
        CatalogEntry(manifest=_manifest("always_long"), strategy_factory=AlwaysLong),
        CatalogEntry(manifest=_manifest("never_trades"), strategy_factory=NeverTrades),
    ]


def _make_runner(kill_switch: KillSwitch | None = None) -> tuple[Engine, LiveMultiModelRunner]:
    fleet = build_fleet(_fleet_entries(), starting_cash=Decimal("10000"))
    clock = ManualClock(START)
    engine = Engine(run_id="fleet-test", book="sandbox", clock=clock)
    risk_model = RiskModel(kill_switch=kill_switch or KillSwitch.in_memory())
    runner = LiveMultiModelRunner(engine=engine, fleet=fleet, symbol=SYMBOL, risk_model=risk_model)
    return engine, runner


def test_build_fleet_is_sorted_and_independent() -> None:
    fleet = build_fleet(_fleet_entries(), starting_cash=Decimal("10000"))
    assert [b.model_id for b in fleet] == ["always_long", "never_trades"]
    assert fleet[0].accounting is not fleet[1].accounting
    assert fleet[0].broker is not fleet[1].broker


def test_audit_hash_chain_verifies_across_the_whole_fleet() -> None:
    engine, runner = _make_runner()
    _drive(engine, runner, _bars(20))
    assert engine.audit.verify()


def test_only_the_trading_model_accrues_trades_the_other_stays_flat() -> None:
    engine, runner = _make_runner()
    _drive(engine, runner, _bars(10))

    trading_book = next(b for b in runner.fleet if b.model_id == "always_long")
    idle_book = next(b for b in runner.fleet if b.model_id == "never_trades")
    assert trading_book.accounting.position_qty(SYMBOL) > 0
    assert idle_book.accounting.position_qty(SYMBOL) == 0
    assert idle_book.accounting.cash == Decimal("10000")  # untouched


def test_aggregate_risk_state_is_the_true_sum_not_one_models_view() -> None:
    """The emitted RiskStateEvent must reflect BOTH books' equity summed --
    not just whichever model happened to process last."""
    engine, runner = _make_runner()
    bars = _bars(10)
    _drive(engine, runner, bars)
    last_bar = bars[-1]

    expected_total_equity = sum(
        (b.accounting.equity({SYMBOL: last_bar.c}) for b in runner.fleet), Decimal("0")
    )
    risk_state_events = [r for r in engine.audit.records if r.type == "RiskStateEvent"]
    assert len(risk_state_events) == 10  # exactly one per bar, not one per model
    last_event = risk_state_events[-1]
    assert Decimal(str(last_event.payload["equity"])) == expected_total_equity
    # sanity: the trading book's equity alone must NOT equal the aggregate
    # (proves this isn't accidentally reading a single model's state)
    trading_book = next(b for b in runner.fleet if b.model_id == "always_long")
    assert trading_book.accounting.equity({SYMBOL: last_bar.c}) != expected_total_equity


class UniverseWatcher:
    """Records every `universe_closes` snapshot it ever sees, but never
    signals -- a control proving foreign-symbol bars reach the strategy
    (feeding cross-sectional models real sibling data) without ever
    reaching the order pipeline for this runner's own symbol."""

    name = "universe_watcher"
    params: dict[str, object] = {}

    def __init__(self) -> None:
        self.seen: list[dict[str, Decimal]] = []

    def on_start(self, ctx: Context) -> None:
        pass

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        self.seen.append(dict(ctx.universe_closes))
        return []

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        pass


def test_foreign_symbol_bars_update_universe_closes_but_never_trade() -> None:
    fleet = build_fleet(
        [CatalogEntry(manifest=_manifest("watcher"), strategy_factory=UniverseWatcher)],
        starting_cash=Decimal("10000"),
    )
    clock = ManualClock(START)
    engine = Engine(run_id="foreign-bar-test", book="sandbox", clock=clock)
    risk_model = RiskModel(kill_switch=KillSwitch.in_memory())
    runner = LiveMultiModelRunner(engine=engine, fleet=fleet, symbol=SYMBOL, risk_model=risk_model)
    watcher = fleet[0].strategy
    assert isinstance(watcher, UniverseWatcher)

    own_bar = _bars(1)[0]
    foreign_bar = MarketEvent(
        exchange="fake", symbol=OTHER_SYMBOL, timeframe="1m",
        ts_open=own_bar.ts_open + timedelta(minutes=1),
        o=Decimal("50"), h=Decimal("51"), l=Decimal("49"), c=Decimal("50"), v=1.0,
        source_version="fake:1",
    )

    _drive(engine, runner, [own_bar, foreign_bar])

    # the foreign bar's close reached the strategy via `universe_closes`...
    assert watcher.seen[-1][OTHER_SYMBOL] == Decimal("50")
    # ...but never touched this runner's own book -- no fill/order for it.
    assert fleet[0].accounting.position_qty(SYMBOL) == 0
    assert not any(r.type == "Order" for r in engine.audit.records)


def test_portfolio_context_absent_leaves_new_state_fields_none() -> None:
    engine, runner = _make_runner()
    book = runner.fleet[0]
    state = runner._portfolio_state(book, _bars(1)[0])  # noqa: SLF001 - white-box test
    assert state.portfolio_equity is None
    assert state.portfolio_gross_notional is None
    assert state.sleeve_notional_used is None


def test_portfolio_context_wiring_rejects_via_shared_aggregate() -> None:
    """A shared `PortfolioContext` already fully deployed (by OTHER books
    this runner doesn't even know about) must reject a new entry here, even
    though this runner's own book is untouched and would otherwise easily
    afford it -- proving the aggregate, not just this book's own figures,
    gates the decision."""
    fleet = build_fleet(_fleet_entries(), starting_cash=Decimal("10000"))
    clock = ManualClock(START)
    engine = Engine(run_id="portfolio-context-test", book="sandbox", clock=clock)
    risk_model = RiskModel(kill_switch=KillSwitch.in_memory())
    portfolio_context = PortfolioContext()
    portfolio_context.refresh(
        book_equity={SYMBOL: Decimal("100")},
        book_notional={SYMBOL: Decimal("100")},  # already fully deployed elsewhere
        book_sleeve={},
    )
    runner = LiveMultiModelRunner(
        engine=engine, fleet=fleet, symbol=SYMBOL, risk_model=risk_model,
        portfolio_context=portfolio_context,
    )

    _drive(engine, runner, _bars(3))

    trading_book = next(b for b in runner.fleet if b.model_id == "always_long")
    assert trading_book.accounting.position_qty(SYMBOL) == 0
    reject_decisions = [
        r for r in engine.audit.records
        if r.type == "RiskDecision" and r.payload["verdict"] == "REJECT"
    ]
    assert any("portfolio_gross_exposure" in r.payload["rule_hits"] for r in reject_decisions)


def test_kill_switch_halts_every_models_new_entries() -> None:
    kill_switch = KillSwitch.in_memory()
    engine, runner = _make_runner(kill_switch)

    # kill BEFORE any bar is processed -- always_long must never get to enter
    kill_switch.trigger(reason="test halt")
    _drive(engine, runner, _bars(5))

    trading_book = next(b for b in runner.fleet if b.model_id == "always_long")
    assert trading_book.accounting.position_qty(SYMBOL) == 0
    reject_decisions = [
        r for r in engine.audit.records
        if r.type == "RiskDecision" and r.payload["verdict"] == "REJECT"
    ]
    assert reject_decisions  # the intent was made and explicitly rejected, not silently dropped
