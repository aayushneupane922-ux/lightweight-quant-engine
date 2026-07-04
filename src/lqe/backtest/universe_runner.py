"""`run_universe_backtest` (V5 M27 "Universe Core", docs/15): runs several
single-instrument `Session`s side by side, one per symbol in a `Universe`,
all sharing one `Engine`/audit log so the whole run reconciles to a single
hash-chained record ("one reconciliation tying every instrument to the
single audit"). Each session keeps trading exactly one symbol (docs/15's
"one book per instrument" design decision, unchanged from the single-
symbol case) -- a missing symbol on a given cycle means no-trade for that
symbol's session this cycle, never a crash or desync for the others; see
`UniverseBacktestResult.missing_counts()` for the honest record of it.

Turning on the full scaled-model catalog across the whole universe is
M28's job ("Wake the Sleeves"); this runner is the plumbing that makes
that possible -- it accepts any `Strategy` per symbol, including a
cross-sectional/stat-arb adapter that can now finally observe its sibling
symbols' real bars (see `models/catalog_scale.py`'s `DEFAULT_UNIVERSE`,
which replaced the fake synthetic universe those adapters used to be
permanently inert against).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from lqe.backtest.make_session import Session
from lqe.core.clock import ReplayClock
from lqe.core.engine import Engine
from lqe.core.events import MarketEvent
from lqe.core.types import Book, RunId, Symbol
from lqe.core.universe import Universe, UniverseCycle
from lqe.execution.commission import BpsCommission
from lqe.execution.fills import MarketOrderFillSimulator
from lqe.execution.paper_broker import PaperBroker
from lqe.execution.slippage import FixedBpsSlippage
from lqe.models.base import Strategy
from lqe.portfolio.accounting import Accounting
from lqe.portfolio.sizing import FixedFractionalSizer
from lqe.risk.model import RiskModel
from lqe.risk.portfolio_context import PortfolioContext


@dataclass
class UniverseBacktestResult:
    engine: Engine
    sessions: dict[Symbol, Session]
    cycles: list[UniverseCycle]

    def missing_counts(self) -> dict[Symbol, int]:
        """How many cycles each symbol was absent from -- the honest,
        inspectable "late/missing, logged" record for this run (docs/15
        M27), rather than a crash or a silently-skipped gap."""
        counts: dict[Symbol, int] = dict.fromkeys(self.sessions, 0)
        for cycle in self.cycles:
            for sym in cycle.missing:
                counts[sym] = counts.get(sym, 0) + 1
        return counts


def run_universe_backtest(
    *,
    run_id: RunId,
    symbols: Sequence[Symbol],
    bars: Sequence[MarketEvent],
    strategies: Mapping[Symbol, Strategy],
    starting_cash: Decimal,
    book: Book = "sandbox",
    risk_models: Mapping[Symbol, RiskModel] | None = None,
    sleeve_of_symbol: Mapping[Symbol, str] | None = None,
    sizer_fraction: Decimal = Decimal("0.1"),
    slippage_bps: float = 5.0,
    commission_bps: float = 10.0,
    max_participation: Decimal = Decimal("1"),
) -> UniverseBacktestResult:
    """`bars` may be in any order across symbols but must be `ts_open`-
    sorted overall (same contract as `Universe.cycles`, and what the
    interleaving fix in `CcxtMarketDataAdapter.stream()` now guarantees for
    live data). `strategies` needs exactly one entry per symbol in
    `symbols` -- each symbol keeps its own single-instrument book.

    `sleeve_of_symbol` (V5 M27) maps each symbol's book to its return-
    driver sleeve for `check_sleeve_concentration`; omit it (or a symbol
    from it) to leave that book's sleeve concentration check a no-op.
    """
    if set(strategies) != set(symbols):
        raise ValueError("`strategies` must have exactly one entry per symbol in `symbols`")

    universe = Universe(list(symbols))
    cycles = list(universe.cycles(bars))
    clock = ReplayClock([cycle.ts_open for cycle in cycles])
    engine = Engine(run_id=run_id, book=book, clock=clock)
    portfolio_context = PortfolioContext()
    sleeve_of_symbol = sleeve_of_symbol or {}

    sessions: dict[Symbol, Session] = {
        sym: Session(
            engine=engine,
            broker=PaperBroker(),
            accounting=Accounting(starting_cash=starting_cash),
            strategy=strategies[sym],
            sizer=FixedFractionalSizer(fraction=sizer_fraction),
            fill_simulator=MarketOrderFillSimulator(
                slippage=FixedBpsSlippage(slippage_bps),
                commission=BpsCommission(bps=commission_bps),
                max_participation=max_participation,
            ),
            risk_model=(risk_models or {}).get(sym) or RiskModel(),
            symbol=sym,
            portfolio_context=portfolio_context,
            sleeve=sleeve_of_symbol.get(sym),
        )
        for sym in symbols
    }

    last_close: dict[Symbol, Decimal] = dict.fromkeys(symbols, Decimal("0"))
    for cycle in cycles:
        engine.tick()
        # Refresh the cross-book snapshot BEFORE this cycle's intents are
        # decided, from each book's accounting state as of the END of the
        # previous cycle -- an intent this cycle is never checked against
        # a same-cycle fill that hasn't happened yet (same no-look-ahead
        # guarantee a single book already has).
        portfolio_context.refresh(
            book_equity={
                sym: sessions[sym].accounting.equity({sym: last_close[sym]}) for sym in symbols
            },
            book_notional={
                sym: abs(sessions[sym].accounting.position_qty(sym)) * last_close[sym]
                for sym in symbols
            },
            book_sleeve=sleeve_of_symbol,
        )
        for bar in cycle.bars:
            last_close[bar.symbol] = bar.c
            engine.emit("MarketEvent", bar)
            # every session sees every bar -- its own symbol's bar gets the
            # full pipeline, everything else is observe-only (`_on_bar`'s
            # own dispatch, identical to the single-session case).
            for session in sessions.values():
                session._on_bar(bar)  # noqa: SLF001 - same-package orchestrator, not external

    return UniverseBacktestResult(engine=engine, sessions=sessions, cycles=cycles)
