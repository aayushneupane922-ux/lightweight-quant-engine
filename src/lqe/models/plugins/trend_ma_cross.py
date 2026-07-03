"""A deterministic long/flat MA-cross strategy (docs/10 M3's one reference
strategy). Enters long on a fast/slow SMA bullish cross, exits to flat on
the bearish cross. Purely a function of closes seen so far — no
look-ahead, no randomness.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


def _sma(closes: list[Decimal], window: int) -> Decimal:
    tail = closes[-window:]
    return sum(tail, Decimal("0")) / Decimal(len(tail))


class TrendMaCross:
    name = "trend_ma_cross"

    def __init__(self, *, symbol: Symbol, fast: int, slow: int) -> None:
        if fast >= slow:
            raise ValueError("fast window must be smaller than slow window")
        self.params: dict[str, object] = {"fast": fast, "slow": slow}
        self._symbol = symbol
        self._fast = fast
        self._slow = slow
        self._closes: list[Decimal] = []
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        self._closes = []
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        self._closes.append(ev.c)
        if len(self._closes) < self._slow:
            return []

        fast_ma = _sma(self._closes, self._fast)
        slow_ma = _sma(self._closes, self._slow)

        if fast_ma > slow_ma and self._position == "FLAT":
            self._position = "LONG"
            return [
                SignalEvent(
                    strategy=self.name,
                    symbol=self._symbol,
                    direction="LONG",
                    strength=1.0,
                    intent_kind="ENTER",
                    bar_ts=ev.ts_open,
                    reason=f"fast_ma({self._fast})={fast_ma} > slow_ma({self._slow})={slow_ma}",
                )
            ]
        if fast_ma <= slow_ma and self._position == "LONG":
            self._position = "FLAT"
            return [
                SignalEvent(
                    strategy=self.name,
                    symbol=self._symbol,
                    direction="FLAT",
                    strength=0.0,
                    intent_kind="EXIT",
                    bar_ts=ev.ts_open,
                    reason=f"fast_ma({self._fast})={fast_ma} <= slow_ma({self._slow})={slow_ma}",
                )
            ]
        return []

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
