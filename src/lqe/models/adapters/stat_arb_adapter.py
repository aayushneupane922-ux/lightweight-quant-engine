"""`stat_arb_adapter` (docs/14 sleeve D, v4): statistical arbitrage beyond
simple OLS-hedge pairs (`StatsmodelsPairsAdapter`, family `pairs`, sleeve
`stat_arb`, docs/03 §3.3). Three native (numpy-only) formulations, each a
genuinely different bet from an OLS hedge ratio and from each other:

- `DistancePairsAdapter` -- the classic Gatev/Goetzmann/Rouwenhorst distance
  method: normalize both legs to a common start over the rolling window,
  trade the *raw* normalized spread's z-score (no hedge ratio estimated),
  long when this instrument has drifted cheap relative to its paired
  partner.
- `LeadLagAdapter` -- a leader/follower spillover bet (e.g. BTC->alt): once
  the leader's trailing return clears a threshold, go long the follower on
  the hypothesis that the move propagates with a lag. Genuinely different
  from a reversion bet -- this one follows the leader's own direction
  rather than fading a spread.
- `BasketArbAdapter` -- index/basket arb: this instrument vs an equal-
  weight synthetic basket of several other symbols, z-scored like the
  distance method but against a basket average rather than one partner.

All three reuse the engine's multi-symbol `Context.universe_closes`/
`Session` extension (docs/14 v4, `backtest/make_session.py`): a per-symbol
close history is built directly from the raw `MarketEvent`s each adapter
observes -- including *other* symbols' bars, which `Session.run` now feeds
to every strategy's `on_market`. A decision is only ever made (and only
ever acted on) on this adapter's *own* symbol's bar, matching
`CrossSectionalAdapter`'s (sleeve C) no-look-ahead, one-book-per-session
pattern.

Long-only, never short, for the same honest reason as sleeve C: this
engine's short-selling path has never been exercised by any model in the
catalog. Declared in each manifest's `failure_modes`, not silently
narrowed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


def _normalized(history: Sequence[float]) -> list[float]:
    base = history[0]
    return [level / base for level in history]


def _zscore(spread: Sequence[float]) -> float | None:
    n = len(spread)
    mean = sum(spread) / n
    variance = sum((s - mean) ** 2 for s in spread) / n
    std = variance**0.5
    if std == 0:
        return None
    return float((spread[-1] - mean) / std)


class DistancePairsAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        partner: Symbol,
        window: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
    ) -> None:
        if partner == symbol:
            raise ValueError("partner must differ from symbol")
        self.name = name
        self.params: dict[str, object] = {
            "window": window, "entry_z": entry_z, "exit_z": exit_z,
        }
        self._symbol = symbol
        self._partner = partner
        self._window = window
        self._entry_z = entry_z
        self._exit_z = exit_z
        self._history: dict[Symbol, list[float]] = {symbol: [], partner: []}
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

        own = self._history[self._symbol]
        theirs = self._history[self._partner]
        if len(own) < self._window or len(theirs) < self._window:
            return []

        norm_own = _normalized(own[-self._window :])
        norm_theirs = _normalized(theirs[-self._window :])
        spread = [a - b for a, b in zip(norm_own, norm_theirs, strict=True)]
        z = _zscore(spread)
        if z is None:
            return []

        target: Literal["LONG", "FLAT"] | None = None
        if z <= -self._entry_z:
            target = "LONG"
        elif z >= self._exit_z:
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
                reason=f"{self.name}: distance spread z={z:.2f} vs {self._partner}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None


class LeadLagAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        leader: Symbol,
        lookback: int = 10,
        entry_return: float = 0.02,
        exit_return: float = 0.0,
    ) -> None:
        if leader == symbol:
            raise ValueError("leader must differ from symbol (this is the follower)")
        self.name = name
        self.params: dict[str, object] = {
            "lookback": lookback, "entry_return": entry_return, "exit_return": exit_return,
        }
        self._symbol = symbol
        self._leader = leader
        self._lookback = lookback
        self._entry_return = entry_return
        self._exit_return = exit_return
        self._history: dict[Symbol, list[float]] = {symbol: [], leader: []}
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

        leader_hist = self._history[self._leader]
        if len(leader_hist) < self._lookback + 1:
            return []

        leader_return = (leader_hist[-1] - leader_hist[-self._lookback - 1]) / (
            leader_hist[-self._lookback - 1]
        )

        target: Literal["LONG", "FLAT"] | None = None
        if leader_return >= self._entry_return:
            target = "LONG"
        elif leader_return <= self._exit_return:
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
                reason=(
                    f"{self.name}: leader {self._leader} {self._lookback}-bar "
                    f"return={leader_return:.4f}"
                ),
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None


class BasketArbAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        basket: Sequence[Symbol],
        window: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
    ) -> None:
        if symbol in basket:
            raise ValueError("symbol must not be a member of its own reference basket")
        if not basket:
            raise ValueError("basket must be non-empty")
        self.name = name
        self.params: dict[str, object] = {
            "window": window, "entry_z": entry_z, "exit_z": exit_z,
        }
        self._symbol = symbol
        self._basket = list(basket)
        self._window = window
        self._entry_z = entry_z
        self._exit_z = exit_z
        self._history: dict[Symbol, list[float]] = {symbol: [], **{sym: [] for sym in basket}}
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

        own = self._history[self._symbol]
        if len(own) < self._window or any(
            len(self._history[sym]) < self._window for sym in self._basket
        ):
            return []

        norm_own = _normalized(own[-self._window :])
        basket_norms = [_normalized(self._history[sym][-self._window :]) for sym in self._basket]
        basket_avg = [sum(values) / len(values) for values in zip(*basket_norms, strict=True)]
        spread = [a - b for a, b in zip(norm_own, basket_avg, strict=True)]
        z = _zscore(spread)
        if z is None:
            return []

        target: Literal["LONG", "FLAT"] | None = None
        if z <= -self._entry_z:
            target = "LONG"
        elif z >= self._exit_z:
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
                reason=f"{self.name}: basket spread z={z:.2f} vs {len(self._basket)}-symbol basket",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
