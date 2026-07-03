"""Decimal-based position + cash accounting (docs/archive/10 §10.7).

Cash-only, no leverage, long/flat only (the MVP restriction — docs/archive/
10 §10.7, HANDOFF.md §6): a SELL that would take a position net-short is a
programming error in this milestone's scope (no strategy shipped yet
attempts to short), so it raises rather than silently going short. Full
long/short accounting and per-bar reconciliation against the audit log are
M5's job (the risk model), not this one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from lqe.core.events import FillEvent
from lqe.core.types import Symbol


@dataclass
class PositionState:
    symbol: Symbol
    qty: Decimal = Decimal("0")
    avg_px: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    fees_paid: Decimal = Decimal("0")


@dataclass
class Accounting:
    starting_cash: Decimal
    cash: Decimal = field(init=False)
    _positions: dict[Symbol, PositionState] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.cash = self.starting_cash

    def position_state(self, symbol: Symbol) -> PositionState:
        return self._positions.setdefault(symbol, PositionState(symbol=symbol))

    def position_qty(self, symbol: Symbol) -> Decimal:
        return self.position_state(symbol).qty

    def apply_fill(self, *, symbol: Symbol, side: Literal["BUY", "SELL"], fill: FillEvent) -> None:
        state = self.position_state(symbol)
        notional = fill.fill_qty * fill.fill_px

        if side == "BUY":
            new_qty = state.qty + fill.fill_qty
            if new_qty > 0:
                state.avg_px = (state.avg_px * state.qty + notional) / new_qty
            state.qty = new_qty
            self.cash -= notional + fill.fee
        else:
            if fill.fill_qty > state.qty:
                raise ValueError(
                    f"cannot sell {fill.fill_qty} against open qty {state.qty} for {symbol!r} "
                    "(shorting is out of scope for this milestone)"
                )
            state.realized_pnl += (fill.fill_px - state.avg_px) * fill.fill_qty
            state.qty -= fill.fill_qty
            if state.qty == 0:
                state.avg_px = Decimal("0")
            self.cash += notional - fill.fee

        state.fees_paid += fill.fee

    def unrealized_pnl(self, symbol: Symbol, mark_price: Decimal) -> Decimal:
        state = self.position_state(symbol)
        return (mark_price - state.avg_px) * state.qty

    def equity(self, marks: dict[Symbol, Decimal]) -> Decimal:
        total = self.cash
        for symbol, state in self._positions.items():
            total += state.qty * marks.get(symbol, state.avg_px)
        return total
