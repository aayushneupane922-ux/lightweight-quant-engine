"""`lqe backtest`'s entry point: build a `ReplayClock` from a bar sequence
and run a `Session` over it via `make_session` (docs/10 M3).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from lqe.backtest.make_session import Session, make_session
from lqe.core.clock import ReplayClock
from lqe.core.events import MarketEvent
from lqe.core.types import RunId, Symbol
from lqe.models.base import Strategy


def run_backtest(
    *,
    run_id: RunId,
    symbol: Symbol,
    bars: Sequence[MarketEvent],
    strategy: Strategy,
    starting_cash: Decimal,
    sizer_fraction: Decimal = Decimal("0.1"),
    slippage_bps: float = 5.0,
    commission_bps: float = 10.0,
    max_participation: Decimal = Decimal("1"),
) -> Session:
    clock = ReplayClock([bar.ts_open for bar in bars])
    session = make_session(
        run_id=run_id,
        book="sandbox",
        clock=clock,
        symbol=symbol,
        strategy=strategy,
        starting_cash=starting_cash,
        sizer_fraction=sizer_fraction,
        slippage_bps=slippage_bps,
        commission_bps=commission_bps,
        max_participation=max_participation,
    )
    session.run(bars)
    return session
