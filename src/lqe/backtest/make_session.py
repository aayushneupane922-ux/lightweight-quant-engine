"""`make_session` — the single function that builds the loop for both
backtest and (later) live paper trading (docs/06 §6.1, GLOSSARY.md).

The no-look-ahead invariant lives in exactly one place: `Session.run`
resolves any orders sitting in the broker's working-order book against the
*current* bar **before** feeding that bar to the strategy. An order
submitted while processing bar `t` therefore always fills against bar
`t+1`'s open at the earliest — never the bar that produced the signal that
created it. `RiskDecision` is a stub `APPROVE` here; the real risk gate
(`risk/model.py`) replaces it in M5 without changing this loop's shape.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Literal

from lqe.core.clock import Clock
from lqe.core.context import Context
from lqe.core.engine import Engine
from lqe.core.events import MarketEvent, OrderIntent, PositionEvent, RiskDecision, SignalEvent
from lqe.core.make_order import make_order
from lqe.core.types import Book, RunId, Symbol
from lqe.execution.commission import BpsCommission
from lqe.execution.fills import MarketOrderFillSimulator
from lqe.execution.paper_broker import PaperBroker
from lqe.execution.slippage import FixedBpsSlippage
from lqe.models.base import Strategy
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer


def _approve(intent: OrderIntent) -> RiskDecision:
    """Stub risk gate (docs/10 M1): always APPROVE. Replaced by the real
    RiskModel in M5 — every order still passes through exactly one choke
    point (`make_order`) regardless of which gate produced the decision."""
    return RiskDecision(intent_ref=intent.intent_id, verdict="APPROVE", approved_qty=intent.qty)


class Session:
    def __init__(
        self,
        *,
        engine: Engine,
        broker: PaperBroker,
        accounting: Accounting,
        strategy: Strategy,
        sizer: FixedFractionalSizer,
        fill_simulator: MarketOrderFillSimulator,
        symbol: Symbol,
    ) -> None:
        self.engine = engine
        self.broker = broker
        self.accounting = accounting
        self._strategy = strategy
        self._sizer = sizer
        self._fill_simulator = fill_simulator
        self._symbol = symbol
        self._strategy.on_start(self._context())

    def _context(self) -> Context:
        return Context(symbol=self._symbol, position_qty=self.accounting.position_qty(self._symbol))

    def run(self, bars: Iterable[MarketEvent]) -> None:
        for bar in bars:
            self.engine.tick()
            self._resolve_working_orders(bar)
            self._process_bar(bar)

    def _resolve_working_orders(self, bar: MarketEvent) -> None:
        for order in list(self.broker.working_orders()):
            fill = self._fill_simulator.fill(order, fill_bar=bar)
            self.engine.emit("FillEvent", fill)
            self.accounting.apply_fill(symbol=self._symbol, side=order.side, fill=fill)
            status: Literal["PARTIALLY_FILLED", "FILLED"] = (
                "PARTIALLY_FILLED" if fill.partial else "FILLED"
            )
            self.broker.mark_filled(order.order_id, status=status)
            self._strategy.on_fill(fill, self._context())

    def _process_bar(self, bar: MarketEvent) -> None:
        self.engine.emit("MarketEvent", bar)
        signals: list[SignalEvent] = self._strategy.on_market(bar, self._context())

        for signal in signals:
            self.engine.emit("SignalEvent", signal)
            qty = self._sizer.size(
                signal=signal,
                equity=self.accounting.equity({self._symbol: bar.c}),
                price=bar.c,
                current_qty=self.accounting.position_qty(self._symbol),
            )
            if qty <= 0:
                continue

            side: Literal["BUY", "SELL"] = "BUY" if signal.direction == "LONG" else "SELL"
            intent = OrderIntent(
                intent_id=f"{signal.strategy}:{signal.symbol}:{bar.ts_open.isoformat()}",
                signal_ref=f"{signal.strategy}:{bar.ts_open.isoformat()}",
                strategy=signal.strategy,
                symbol=signal.symbol,
                side=side,
                qty=qty,
                order_type="MARKET",
                idempotency_key=f"{signal.strategy}:{bar.ts_open.isoformat()}",
                reason=signal.reason,
            )
            self.engine.emit("OrderIntent", intent)
            decision = _approve(intent)
            self.engine.emit("RiskDecision", decision)
            order = make_order(intent, decision)
            self.engine.emit("Order", order)
            self.broker.submit(order)

        position = self.accounting.position_state(self._symbol)
        self.engine.emit(
            "PositionEvent",
            PositionEvent(
                symbol=self._symbol,
                qty=position.qty,
                avg_px=position.avg_px,
                realized_pnl=position.realized_pnl,
                unrealized_pnl=self.accounting.unrealized_pnl(self._symbol, bar.c),
                fees_paid=position.fees_paid,
            ),
        )


def make_session(
    *,
    run_id: RunId,
    book: Book,
    clock: Clock,
    symbol: Symbol,
    strategy: Strategy,
    starting_cash: Decimal,
    sizer_fraction: Decimal = Decimal("0.1"),
    slippage_bps: float = 5.0,
    commission_bps: float = 10.0,
    max_participation: Decimal = Decimal("1"),
) -> Session:
    engine = Engine(run_id=run_id, book=book, clock=clock)
    broker = PaperBroker()
    accounting = Accounting(starting_cash=starting_cash)
    sizer = FixedFractionalSizer(fraction=sizer_fraction)
    fill_simulator = MarketOrderFillSimulator(
        slippage=FixedBpsSlippage(slippage_bps),
        commission=BpsCommission(bps=commission_bps),
        max_participation=max_participation,
    )
    return Session(
        engine=engine,
        broker=broker,
        accounting=accounting,
        strategy=strategy,
        sizer=sizer,
        fill_simulator=fill_simulator,
        symbol=symbol,
    )
