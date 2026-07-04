"""`LiveMultiModelRunner`/`build_fleet` (post-v1.0 extension): every model
gets its own fully independent paper book, all sharing one hash-chained
engine and one kill switch. Two trivial, fully deterministic fake
strategies (not real catalog indicators) make the fleet-level arithmetic and
attribution easy to verify exactly, rather than depending on real indicator
signal timing.
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

SYMBOL = "BTC-USDT"
START = datetime(2026, 1, 1, tzinfo=UTC)


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
    clock = engine.clock
    for bar in _bars(20):
        clock.set(bar.ts_open)  # type: ignore[attr-defined]
        runner.process_bar(bar)
    assert engine.audit.verify()


def test_only_the_trading_model_accrues_trades_the_other_stays_flat() -> None:
    engine, runner = _make_runner()
    clock = engine.clock
    for bar in _bars(10):
        clock.set(bar.ts_open)  # type: ignore[attr-defined]
        runner.process_bar(bar)

    trading_book = next(b for b in runner.fleet if b.model_id == "always_long")
    idle_book = next(b for b in runner.fleet if b.model_id == "never_trades")
    assert trading_book.accounting.position_qty(SYMBOL) > 0
    assert idle_book.accounting.position_qty(SYMBOL) == 0
    assert idle_book.accounting.cash == Decimal("10000")  # untouched


def test_aggregate_risk_state_is_the_true_sum_not_one_models_view() -> None:
    """The emitted RiskStateEvent must reflect BOTH books' equity summed --
    not just whichever model happened to process last."""
    engine, runner = _make_runner()
    clock = engine.clock
    last_bar = None
    for bar in _bars(10):
        clock.set(bar.ts_open)  # type: ignore[attr-defined]
        runner.process_bar(bar)
        last_bar = bar
    assert last_bar is not None

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


def test_kill_switch_halts_every_models_new_entries() -> None:
    kill_switch = KillSwitch.in_memory()
    engine, runner = _make_runner(kill_switch)
    clock = engine.clock

    # kill BEFORE any bar is processed -- always_long must never get to enter
    kill_switch.trigger(reason="test halt")
    for bar in _bars(5):
        clock.set(bar.ts_open)  # type: ignore[attr-defined]
        runner.process_bar(bar)

    trading_book = next(b for b in runner.fleet if b.model_id == "always_long")
    assert trading_book.accounting.position_qty(SYMBOL) == 0
    reject_decisions = [
        r for r in engine.audit.records
        if r.type == "RiskDecision" and r.payload["verdict"] == "REJECT"
    ]
    assert reject_decisions  # the intent was made and explicitly rejected, not silently dropped
