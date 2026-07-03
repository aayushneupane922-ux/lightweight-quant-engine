"""`make_session` — the single function that builds the loop for both
backtest and (later) live paper trading (docs/06 §6.1, GLOSSARY.md).

The no-look-ahead invariant lives in exactly one place: `Session.run`
resolves any orders sitting in the broker's working-order book against the
*current* bar **before** feeding that bar to the strategy. An order
submitted while processing bar `t` therefore always fills against bar
`t+1`'s open at the earliest — never the bar that produced the signal that
created it.

The risk gate is the real `RiskModel` (M5) — the single choke point before
`make_order`; a REJECT is never passed to `make_order` (which would raise),
it's simply not converted into an order. Reconciliation runs every bar:
the running ledger is compared against an independent replay of every fill
so far, and any mismatch halts the run via `ReconciliationError` rather
than continuing on possibly-corrupt state.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from lqe.core.clock import Clock
from lqe.core.config import assert_paper_only
from lqe.core.context import Context
from lqe.core.engine import Engine
from lqe.core.events import MarketEvent, OrderIntent, PositionEvent, SignalEvent
from lqe.core.make_order import make_order
from lqe.core.types import Book, RunId, Symbol
from lqe.execution.commission import BpsCommission
from lqe.execution.fills import MarketOrderFillSimulator
from lqe.execution.paper_broker import PaperBroker
from lqe.execution.slippage import FixedBpsSlippage
from lqe.models.base import Strategy
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer
from lqe.risk.de_risk import DeRiskController
from lqe.risk.model import RiskModel
from lqe.risk.reconciliation import FillRecord, reconcile
from lqe.risk.rules import PortfolioState


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
        risk_model: RiskModel,
        de_risk: DeRiskController | None = None,
        symbol: Symbol,
    ) -> None:
        assert_paper_only(broker.is_paper)
        self.engine = engine
        self.broker = broker
        self.accounting = accounting
        self.risk_model = risk_model
        self.de_risk = de_risk or DeRiskController()
        self._strategy = strategy
        self._sizer = sizer
        self._fill_simulator = fill_simulator
        self._symbol = symbol
        # Analytics telemetry (docs/10 M4): one equity mark per bar, one
        # trade_pnl per realized (SELL) fill, one notional per fill.
        self.equity_curve: list[Decimal] = [accounting.cash]
        self.trade_pnls: list[float] = []
        self.trade_notionals: list[Decimal] = []
        # Risk/reconciliation bookkeeping (M5).
        self._fills_history: list[FillRecord] = []
        self._peak_equity: Decimal = accounting.cash
        self._day_anchor: date | None = None
        self._day_start_equity: Decimal = accounting.cash
        self._order_timestamps: list[datetime] = []
        self._intent_keys: set[str] = set()
        self._strategy.on_start(self._context())

    def _context(self) -> Context:
        return Context(symbol=self._symbol, position_qty=self.accounting.position_qty(self._symbol))

    def run(self, bars: Iterable[MarketEvent]) -> None:
        for bar in bars:
            self.engine.tick()
            self._resolve_working_orders(bar)
            self._update_day_anchor(bar)
            self._reconcile()
            self._emit_risk_state(bar)
            self._process_bar(bar)

    def _update_day_anchor(self, bar: MarketEvent) -> None:
        bar_date = bar.ts_open.date()
        if self._day_anchor != bar_date:
            self._day_anchor = bar_date
            self._day_start_equity = self.accounting.equity({self._symbol: bar.c})
        equity = self.accounting.equity({self._symbol: bar.c})
        self._peak_equity = max(self._peak_equity, equity)

    def _reconcile(self) -> None:
        reconcile(
            live=self.accounting,
            starting_cash=self.accounting.starting_cash,
            symbol=self._symbol,
            fills=self._fills_history,
        )

    def _portfolio_state(self, bar: MarketEvent) -> PortfolioState:
        equity = self.accounting.equity({self._symbol: bar.c})
        position_qty = self.accounting.position_qty(self._symbol)
        return PortfolioState(
            symbol=self._symbol,
            equity=equity,
            cash=self.accounting.cash,
            peak_equity=self._peak_equity,
            daily_pnl=equity - self._day_start_equity,
            position_qty=position_qty,
            reference_price=bar.c,
            last_data_ts=bar.ts_open,
            now_ts=bar.ts_open,
            recent_order_ts=tuple(self._order_timestamps),
            recent_intent_keys=frozenset(self._intent_keys),
            strategy_notional_used=position_qty * bar.c,
            open_orders=len(self.broker.working_orders()),
        )

    def _emit_risk_state(self, bar: MarketEvent) -> None:
        state = self._portfolio_state(bar)
        risk_state_event = self.risk_model.on_bar(state)
        self.engine.emit("RiskStateEvent", risk_state_event)

    def _resolve_working_orders(self, bar: MarketEvent) -> None:
        for order in list(self.broker.working_orders()):
            fill = self._fill_simulator.fill(order, fill_bar=bar)
            self.engine.emit("FillEvent", fill)
            realized_before = self.accounting.position_state(self._symbol).realized_pnl
            self.accounting.apply_fill(symbol=self._symbol, side=order.side, fill=fill)
            self._fills_history.append((order.side, fill))
            if order.side == "SELL":
                realized_after = self.accounting.position_state(self._symbol).realized_pnl
                self.trade_pnls.append(float(realized_after - realized_before))
            self.trade_notionals.append(fill.fill_qty * fill.fill_px)
            status: Literal["PARTIALLY_FILLED", "FILLED"] = (
                "PARTIALLY_FILLED" if fill.partial else "FILLED"
            )
            self.broker.mark_filled(order.order_id, filled_qty=fill.fill_qty, status=status)
            self._strategy.on_fill(fill, self._context())

    def _process_bar(self, bar: MarketEvent) -> None:
        self.engine.emit("MarketEvent", bar)
        signals: list[SignalEvent] = self._strategy.on_market(bar, self._context())

        for signal in signals:
            self.engine.emit("SignalEvent", signal)
            # A de-risked (paused/retired) model may still exit an existing
            # position — only NEW entries are blocked (docs/02 §2.4).
            entering = signal.intent_kind == "ENTER"
            if entering and not self.de_risk.may_open_new_entries(signal.strategy):
                continue
            qty = self._sizer.size(
                signal=signal,
                equity=self.accounting.equity({self._symbol: bar.c}),
                price=bar.c,
                current_qty=self.accounting.position_qty(self._symbol),
            )
            if entering:
                qty *= self.de_risk.exposure_multiplier(signal.strategy)
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
            decision = self.risk_model.check(intent, self._portfolio_state(bar))
            self.engine.emit("RiskDecision", decision)
            if decision.verdict == "REJECT":
                continue
            order = make_order(intent, decision)
            self.engine.emit("Order", order)
            self.broker.submit(order)
            self._order_timestamps.append(bar.ts_open)
            self._intent_keys.add(intent.idempotency_key)

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
        self.equity_curve.append(self.accounting.equity({self._symbol: bar.c}))


def make_session(
    *,
    run_id: RunId,
    book: Book,
    clock: Clock,
    symbol: Symbol,
    strategy: Strategy,
    starting_cash: Decimal,
    risk_model: RiskModel | None = None,
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
        risk_model=risk_model or RiskModel(),
        symbol=symbol,
    )
