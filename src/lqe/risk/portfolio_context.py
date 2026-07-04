"""`PortfolioContext` (V5 M27 "Universe Core", docs/15): a small, mutable,
cross-book snapshot a multi-instrument orchestrator
(`backtest.universe_runner.run_universe_backtest`) refreshes once per
bar-cycle and shares across several single-symbol `Session`s. Each
`Session` reads it when building its own `risk.rules.PortfolioState` for a
risk check -- `check_portfolio_gross_exposure`/`check_sleeve_concentration`
are the only rules that ever look at it; every other rule (position
limits, cash, per-strategy budget, stale data, ...) still uses that book's
own real figures, unchanged.

Not shared/threaded at all in the single-symbol case -- `Session.__init__`
defaults `portfolio_context=None`, and the two new rules are then no-ops.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from lqe.core.types import Symbol


@dataclass
class PortfolioContext:
    equity: Decimal = Decimal("0")
    gross_notional: Decimal = Decimal("0")
    _sleeve_notional: dict[str, Decimal] = field(default_factory=dict)

    def refresh(
        self,
        *,
        book_equity: Mapping[Symbol, Decimal],
        book_notional: Mapping[Symbol, Decimal],
        book_sleeve: Mapping[Symbol, str | None],
    ) -> None:
        """Called once per bar-cycle by the orchestrator, using each
        book's accounting state as of the *previous* cycle -- an intent
        this cycle is always checked against state before this cycle's
        own bars/fills, same no-look-ahead guarantee as a single book."""
        self.equity = sum(book_equity.values(), Decimal("0"))
        self.gross_notional = sum(book_notional.values(), Decimal("0"))
        totals: dict[str, Decimal] = {}
        for symbol, notional in book_notional.items():
            sleeve = book_sleeve.get(symbol)
            if sleeve is None:
                continue
            totals[sleeve] = totals.get(sleeve, Decimal("0")) + notional
        self._sleeve_notional = totals

    def sleeve_notional(self, sleeve: str | None) -> Decimal | None:
        if sleeve is None:
            return None
        return self._sleeve_notional.get(sleeve, Decimal("0"))
