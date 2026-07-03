"""Proves `Session` actually consults the `DeRiskController` — not just
that the controller works in isolation (docs/10 M5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.backtest.make_session import make_session
from lqe.core.clock import ReplayClock
from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol
from lqe.risk.de_risk import DeRiskController

SYMBOL: Symbol = "BTC-USDT"


class _ScriptedStrategy:
    """Emits a fixed ENTER/EXIT script by bar index, ignoring price."""

    name = "scripted"
    params: dict[str, object] = {}

    def __init__(self, *, symbol: Symbol, script: dict[int, str]) -> None:
        self._symbol = symbol
        self._script = script
        self._bar_idx = -1

    def on_start(self, ctx: Context) -> None:
        self._bar_idx = -1

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        self._bar_idx += 1
        action = self._script.get(self._bar_idx)
        if action is None:
            return []
        if action == "ENTER":
            return [
                SignalEvent(
                    strategy=self.name, symbol=self._symbol, direction="LONG", strength=1.0,
                    intent_kind="ENTER", bar_ts=ev.ts_open, reason="scripted",
                )
            ]
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction="FLAT", strength=0.0,
                intent_kind="EXIT", bar_ts=ev.ts_open, reason="scripted",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None


def _bars(n: int) -> list[MarketEvent]:
    return [
        MarketEvent(
            exchange="binance", symbol=SYMBOL, timeframe="1m",
            ts_open=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            o=Decimal("100"), h=Decimal("101"), l=Decimal("99"), c=Decimal("100"),
            v=1000.0, source_version="test",
        )
        for i in range(n)
    ]


def test_paused_model_blocks_new_entries_but_not_exits() -> None:
    bars = _bars(5)
    # ENTER at bar 0 (fills bar 1), EXIT at bar 3 (fills bar 4)
    strategy = _ScriptedStrategy(symbol=SYMBOL, script={0: "ENTER", 3: "EXIT"})
    de_risk = DeRiskController()
    clock = ReplayClock([b.ts_open for b in bars])
    session = make_session(
        run_id="de-risk-test", book="sandbox", clock=clock, symbol=SYMBOL, strategy=strategy,
        starting_cash=Decimal("100000"),
    )
    session.de_risk = de_risk

    session.engine.tick()
    session._resolve_working_orders(bars[0])
    session._process_bar(bars[0])  # ENTER signal submitted here

    # pause BEFORE the entry fills and BEFORE the exit bar arrives
    de_risk.apply(model_id=strategy.name, action="PAUSE", reason="test")

    for bar in bars[1:]:
        session.engine.tick()
        session._resolve_working_orders(bar)
        session._process_bar(bar)

    order_events = [e for e in session.engine.audit.records if e.type == "Order"]
    sides = [e.payload["side"] for e in order_events]
    assert sides == ["BUY", "SELL"]  # the entry (pre-pause) and the exit (post-pause) both happened
    assert session.accounting.position_qty(SYMBOL) == Decimal("0")  # exit fully closed the position


def test_paused_model_never_opens_a_fresh_entry() -> None:
    bars = _bars(3)
    strategy = _ScriptedStrategy(symbol=SYMBOL, script={1: "ENTER"})
    de_risk = DeRiskController()
    clock = ReplayClock([b.ts_open for b in bars])
    session = make_session(
        run_id="de-risk-test-2", book="sandbox", clock=clock, symbol=SYMBOL, strategy=strategy,
        starting_cash=Decimal("100000"),
    )
    session.de_risk = de_risk
    de_risk.apply(model_id=strategy.name, action="PAUSE", reason="paused from the start")

    session.run(bars)

    order_events = [e for e in session.engine.audit.records if e.type == "Order"]
    assert order_events == []
    assert session.accounting.position_qty(SYMBOL) == Decimal("0")
