"""Live multi-model paper trading (post-v1.0 extension, user-requested — see
HANDOFF.md / COMPONENT-GUIDE.md). Runs every admitted catalog model as its
own fully independent paper book (own strategy, own `PaperBroker`, own
`Accounting`, own simulated starting cash) against the *same* real-time bar
feed, inside ONE shared, hash-chained `Engine`/`AuditLog` — so the desk can
render the whole fleet from a single audit log, exactly the way
`storage.state_reader` already expects.

Still paper-only, still one choke point: `PaperBroker` is still the only
`ExecutionAdapter`, `make_order` is still the only `Order` constructor, and
one shared `KillSwitch` (passed into a single shared `RiskModel`) halts every
model's new entries at once — there is no per-model kill.

**Why one aggregate `RiskStateEvent` per bar, not 48.** `RiskStateEvent`
(docs/11 §11.3) intentionally carries no per-model identifier — it was
designed for a single-book session. Rather than changing that audited event
schema (and touching every place that already depends on its shape), this
runner computes ONE honest, fleet-wide aggregate each bar — summed equity,
summed cash, summed gross exposure, the peak/day-start of that SUM over time
(not the sum of each model's own peak, which would overstate it) — and emits
exactly one `RiskStateEvent` from it. Per-model attribution for the desk
still flows through the existing strategy-tagged `SignalEvent`/`OrderIntent`/
`Order`/`FillEvent` chain, exactly as `storage.state_reader._Reconstruction`
already consumes it for the Floor view — nothing there needed to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from lqe.core.context import Context
from lqe.core.engine import Engine
from lqe.core.events import MarketEvent, OrderIntent
from lqe.core.make_order import make_order
from lqe.core.types import Symbol
from lqe.execution.commission import BpsCommission
from lqe.execution.fills import MarketOrderFillSimulator
from lqe.execution.paper_broker import PaperBroker
from lqe.execution.slippage import FixedBpsSlippage
from lqe.models.base import Strategy
from lqe.models.catalog import CatalogEntry
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer
from lqe.risk.model import RiskModel
from lqe.risk.reconciliation import FillRecord, reconcile
from lqe.risk.rules import PortfolioState


@dataclass
class ModelBook:
    """One model's fully independent simulated book."""

    model_id: str
    strategy: Strategy
    broker: PaperBroker
    accounting: Accounting
    sizer: FixedFractionalSizer
    fill_simulator: MarketOrderFillSimulator
    fills_history: list[FillRecord] = field(default_factory=list)
    peak_equity: Decimal = Decimal("0")
    day_start_equity: Decimal = Decimal("0")
    day_anchor: date | None = None
    order_timestamps: list = field(default_factory=list)  # type: ignore[type-arg]
    intent_keys: set[str] = field(default_factory=set)


def build_fleet(
    entries: list[CatalogEntry],
    *,
    starting_cash: Decimal,
    slippage_bps: float = 5.0,
    commission_bps: float = 10.0,
    sizer_fraction: Decimal = Decimal("0.1"),
) -> list[ModelBook]:
    """One `ModelBook` per admitted catalog entry, in a stable
    (model-id-sorted) order — so a run's model ordering is deterministic
    regardless of catalog construction order."""
    fleet = [
        ModelBook(
            model_id=entry.manifest.id,
            strategy=entry.strategy_factory(),
            broker=PaperBroker(),
            accounting=Accounting(starting_cash=starting_cash),
            sizer=FixedFractionalSizer(fraction=sizer_fraction),
            fill_simulator=MarketOrderFillSimulator(
                slippage=FixedBpsSlippage(slippage_bps),
                commission=BpsCommission(bps=commission_bps),
            ),
            peak_equity=starting_cash,
            day_start_equity=starting_cash,
        )
        for entry in entries
    ]
    fleet.sort(key=lambda b: b.model_id)
    return fleet


class LiveMultiModelRunner:
    """Feeds one shared `Engine` from N independent `ModelBook`s. Call
    `process_bar` once per new live (or replayed) bar."""

    def __init__(
        self, *, engine: Engine, fleet: list[ModelBook], symbol: Symbol, risk_model: RiskModel
    ) -> None:
        self.engine = engine
        self.fleet = fleet
        self.symbol = symbol
        self.risk_model = risk_model
        self._started = False
        self._fleet_peak_equity = sum((b.accounting.cash for b in fleet), Decimal("0"))
        self._fleet_day_anchor: date | None = None
        self._fleet_day_start_equity = self._fleet_peak_equity

    def start(self) -> None:
        ctx = Context(symbol=self.symbol, position_qty=Decimal("0"))
        for book in self.fleet:
            book.strategy.on_start(ctx)
        self._started = True

    def process_bar(self, bar: MarketEvent) -> None:
        if not self._started:
            self.start()
        self.engine.tick()
        self.engine.emit("MarketEvent", bar)

        for book in self.fleet:
            self._resolve_working_orders(book, bar)
            self._update_day_anchor(book, bar)
            reconcile(
                live=book.accounting,
                starting_cash=book.accounting.starting_cash,
                symbol=self.symbol,
                fills=book.fills_history,
            )
            self._process_signals(book, bar)

        self._emit_aggregate_risk_state(bar)

    # -- per-model ----------------------------------------------------------

    def _resolve_working_orders(self, book: ModelBook, bar: MarketEvent) -> None:
        for order in list(book.broker.working_orders()):
            fill = book.fill_simulator.fill(order, fill_bar=bar)
            self.engine.emit("FillEvent", fill)
            book.accounting.apply_fill(symbol=self.symbol, side=order.side, fill=fill)
            book.fills_history.append((order.side, fill))
            status: Literal["PARTIALLY_FILLED", "FILLED"] = (
                "PARTIALLY_FILLED" if fill.partial else "FILLED"
            )
            book.broker.mark_filled(order.order_id, filled_qty=fill.fill_qty, status=status)
            ctx = Context(
                symbol=self.symbol, position_qty=book.accounting.position_qty(self.symbol)
            )
            book.strategy.on_fill(fill, ctx)

    def _update_day_anchor(self, book: ModelBook, bar: MarketEvent) -> None:
        bar_date = bar.ts_open.date()
        if book.day_anchor != bar_date:
            book.day_anchor = bar_date
            book.day_start_equity = book.accounting.equity({self.symbol: bar.c})
        equity = book.accounting.equity({self.symbol: bar.c})
        book.peak_equity = max(book.peak_equity, equity)

    def _process_signals(self, book: ModelBook, bar: MarketEvent) -> None:
        ctx = Context(symbol=self.symbol, position_qty=book.accounting.position_qty(self.symbol))
        signals = book.strategy.on_market(bar, ctx)
        for signal in signals:
            self.engine.emit("SignalEvent", signal)
            equity = book.accounting.equity({self.symbol: bar.c})
            qty = book.sizer.size(
                signal=signal, equity=equity, price=bar.c,
                current_qty=book.accounting.position_qty(self.symbol),
            )
            if qty <= 0:
                continue
            side: Literal["BUY", "SELL"] = "BUY" if signal.direction == "LONG" else "SELL"
            intent = OrderIntent(
                intent_id=f"{signal.strategy}:{signal.symbol}:{bar.ts_open.isoformat()}",
                signal_ref=f"{signal.strategy}:{bar.ts_open.isoformat()}",
                strategy=signal.strategy, symbol=signal.symbol, side=side, qty=qty,
                order_type="MARKET",
                idempotency_key=f"{signal.strategy}:{bar.ts_open.isoformat()}",
                reason=signal.reason,
            )
            self.engine.emit("OrderIntent", intent)
            decision = self.risk_model.check(intent, self._portfolio_state(book, bar))
            self.engine.emit("RiskDecision", decision)
            if decision.verdict == "REJECT":
                continue
            order = make_order(intent, decision)
            self.engine.emit("Order", order)
            book.broker.submit(order)
            book.order_timestamps.append(bar.ts_open)
            book.intent_keys.add(intent.idempotency_key)

    def _portfolio_state(self, book: ModelBook, bar: MarketEvent) -> PortfolioState:
        equity = book.accounting.equity({self.symbol: bar.c})
        position_qty = book.accounting.position_qty(self.symbol)
        return PortfolioState(
            symbol=self.symbol, equity=equity, cash=book.accounting.cash,
            peak_equity=book.peak_equity, daily_pnl=equity - book.day_start_equity,
            position_qty=position_qty, reference_price=bar.c,
            last_data_ts=bar.ts_open, now_ts=bar.ts_open,
            recent_order_ts=tuple(book.order_timestamps),
            recent_intent_keys=frozenset(book.intent_keys),
            strategy_notional_used=position_qty * bar.c,
            open_orders=len(book.broker.working_orders()),
        )

    # -- fleet aggregate ------------------------------------------------------

    def _emit_aggregate_risk_state(self, bar: MarketEvent) -> None:
        equity = sum(
            (b.accounting.equity({self.symbol: bar.c}) for b in self.fleet), Decimal("0")
        )
        cash = sum((b.accounting.cash for b in self.fleet), Decimal("0"))
        gross_notional = sum(
            (abs(b.accounting.position_qty(self.symbol)) * bar.c for b in self.fleet),
            Decimal("0"),
        )
        open_orders = sum(len(b.broker.working_orders()) for b in self.fleet)

        bar_date = bar.ts_open.date()
        if self._fleet_day_anchor != bar_date:
            self._fleet_day_anchor = bar_date
            self._fleet_day_start_equity = equity
        self._fleet_peak_equity = max(self._fleet_peak_equity, equity)

        # `PortfolioState.gross_exposure` is a *ratio* (position_qty *
        # reference_price / equity) -- there's no single fleet position_qty,
        # so we back-solve a synthetic value that reproduces the true
        # fleet-wide exposure ratio when that property is read. Used only
        # for this one aggregate on_bar() call, never for any per-model gate.
        synthetic_qty = gross_notional / bar.c if bar.c > 0 else Decimal("0")
        aggregate_state = PortfolioState(
            symbol=self.symbol, equity=equity, cash=cash,
            peak_equity=self._fleet_peak_equity,
            daily_pnl=equity - self._fleet_day_start_equity,
            position_qty=synthetic_qty, reference_price=bar.c,
            last_data_ts=bar.ts_open, now_ts=bar.ts_open,
            open_orders=open_orders,
        )
        risk_state_event = self.risk_model.on_bar(aggregate_state)
        self.engine.emit("RiskStateEvent", risk_state_event)
