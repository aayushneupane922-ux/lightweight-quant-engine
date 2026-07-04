"""`BasisCarryAdapter` (docs/14 sleeve F, v4): cash-and-carry basis --
spot vs. perp price divergence.

Reuses the engine's multi-symbol `Context.universe_closes`/`Session`
extension (docs/14 v4, `backtest/make_session.py`) built for sleeve C/D:
the perp instrument is observed as a *foreign* symbol's `MarketEvent`
(its OHLCV comes from the same ccxt adapter used for spot -- a perpetual
swap market is fetched via `fetch_ohlcv` exactly like a spot market, just
against a different native symbol registered in the `SymbolRegistry`). No
further engine changes needed.

**Honesty note** (same as `funding_carry_adapter.py`): the textbook
cash-and-carry trade is long spot / short perp, converging as the basis
narrows toward expiry -- market-neutral. This engine's short-selling path
is out of scope, so this adapter only ever holds the spot leg, gated by
how wide the observed basis is. It is a **directional bet on spot,
informed by a basis signal**, not a market-neutral basis capture.
Declared in the manifest's `failure_modes`.
"""

from __future__ import annotations

from typing import Literal

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


class BasisCarryAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        perp_symbol: Symbol,
        entry_basis: float = 0.001,
        exit_basis: float = 0.0,
    ) -> None:
        if perp_symbol == symbol:
            raise ValueError("perp_symbol must differ from symbol")
        self.name = name
        self.params: dict[str, object] = {"entry_basis": entry_basis, "exit_basis": exit_basis}
        self._symbol = symbol
        self._perp_symbol = perp_symbol
        self._entry_basis = entry_basis
        self._exit_basis = exit_basis
        self._history: dict[Symbol, list[float]] = {symbol: [], perp_symbol: []}
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        for sym in self._history:
            self._history[sym] = []
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol not in self._history:
            return []
        self._history[ev.symbol].append(float(ev.c))
        if ev.symbol != self._symbol:
            return []

        perp_hist = self._history[self._perp_symbol]
        if not perp_hist:
            return []

        spot = self._history[self._symbol][-1]
        perp = perp_hist[-1]
        if spot == 0:
            return []
        basis = (perp - spot) / spot

        target: Literal["LONG", "FLAT"] | None = None
        if basis >= self._entry_basis:
            target = "LONG"
        elif basis <= self._exit_basis:
            target = "FLAT"
        if target is None or target == self._position:
            return []

        self._position = target
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction=target,
                strength=1.0 if target == "LONG" else 0.0,
                intent_kind="ENTER" if target == "LONG" else "EXIT",
                bar_ts=ev.ts_open,
                reason=f"{self.name}: basis={basis:.5f} vs {self._perp_symbol}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
