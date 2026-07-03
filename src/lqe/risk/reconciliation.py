"""Reconciliation & rebuild-from-audit (docs/archive/10 §10.10, docs/10 M5).

Each bar (and on shutdown): independently recompute cash/position from the
full fill history and assert it matches the running ledger. Everything is
`Decimal`, so a mismatch is a real bug — a fill applied twice, missed, or
misattributed — not a rounding nuance; it halts rather than drifting
silently. `rebuild_from_audit` is the same replay mechanism run against
nothing but a persisted audit log, proving state is recoverable after a
restart without the live `Accounting` object surviving the crash.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Literal

from lqe.core.engine import AuditLog
from lqe.core.errors import ReconciliationError
from lqe.core.events import FillEvent, Order
from lqe.core.types import Symbol
from lqe.portfolio.accounting import Accounting

FillRecord = tuple[Literal["BUY", "SELL"], FillEvent]


def replay_fills(
    *, starting_cash: Decimal, symbol: Symbol, fills: Sequence[FillRecord]
) -> Accounting:
    accounting = Accounting(starting_cash=starting_cash)
    for side, fill in fills:
        accounting.apply_fill(symbol=symbol, side=side, fill=fill)
    return accounting


def reconcile(
    *, live: Accounting, starting_cash: Decimal, symbol: Symbol, fills: Sequence[FillRecord]
) -> None:
    rebuilt = replay_fills(starting_cash=starting_cash, symbol=symbol, fills=fills)
    live_state = live.position_state(symbol)
    rebuilt_state = rebuilt.position_state(symbol)
    if rebuilt.cash != live.cash or rebuilt_state.qty != live_state.qty:
        raise ReconciliationError(
            f"reconciliation mismatch for {symbol!r}: "
            f"rebuilt(cash={rebuilt.cash}, qty={rebuilt_state.qty}) != "
            f"live(cash={live.cash}, qty={live_state.qty})"
        )


def rebuild_from_audit(path: Path, *, starting_cash: Decimal, symbol: Symbol) -> Accounting:
    log = AuditLog.from_jsonl(path)
    orders_by_id: dict[str, Order] = {}
    fills: list[FillRecord] = []
    for envelope in log.records:
        if envelope.type == "Order":
            order = Order.model_validate(envelope.payload)
            orders_by_id[order.order_id] = order
        elif envelope.type == "FillEvent":
            fill = FillEvent.model_validate(envelope.payload)
            matching_order = orders_by_id.get(fill.order_id)
            if matching_order is None:
                raise ReconciliationError(f"FillEvent for unknown order_id {fill.order_id!r}")
            fills.append((matching_order.side, fill))
    return replay_fills(starting_cash=starting_cash, symbol=symbol, fills=fills)
