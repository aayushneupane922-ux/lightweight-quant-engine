"""`StatsmodelsPairsAdapter` (docs/03 §3.3, family: pairs). `statsmodels`
(BSD-3) is kept in the optional `models` extra, not the base runtime
(`pyproject.toml`) — imported lazily here so a base install never needs it,
and a missing install quarantines cleanly at intake instead of crashing.

Trades the OLS-hedge spread between the tracked `symbol` and a fixed
`hedge_closes` reference series (e.g. a correlated instrument's own close
history, supplied once at construction): long the spread when it's z-score
cheap, flat once it reverts. The current engine is single-instrument
(docs/10 M11 is where real multi-instrument accounting lands), so this
adapter only ever *decides* for `symbol`, using the hedge series as a fixed
input rather than a second live feed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


def _import_statsmodels() -> object:
    try:
        import statsmodels.api as sm
    except ImportError as exc:
        raise ImportError(
            "StatsmodelsPairsAdapter requires the optional 'models' extra: "
            "pip install '.[models]'"
        ) from exc
    return sm


class StatsmodelsPairsAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        hedge_closes: Sequence[float],
        window: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        refit_every: int = 1,
    ) -> None:
        self._sm = _import_statsmodels()
        self.name = name
        self.params: dict[str, object] = {
            "window": window, "entry_z": entry_z, "exit_z": exit_z, "refit_every": refit_every,
        }
        self._symbol = symbol
        self._hedge_closes = list(hedge_closes)
        self._window = window
        self._entry_z = entry_z
        self._exit_z = exit_z
        self._refit_every = refit_every
        self._bars_since_fit = 0
        self._hedge_ratio: float | None = None
        self._closes: list[float] = []
        self._position: Literal["FLAT", "LONG"] = "FLAT"

    def on_start(self, ctx: Context) -> None:
        self._closes.clear()
        self._bars_since_fit = 0
        self._hedge_ratio = None
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        self._closes.append(float(ev.c))
        i = len(self._closes) - 1
        if i >= len(self._hedge_closes) or len(self._closes) < self._window:
            return []

        y = np.array(self._closes[-self._window :])
        x = np.array(self._hedge_closes[i - self._window + 1 : i + 1])
        # The OLS refit is the expensive part; the cached hedge ratio is
        # reused between refits (same schedule pattern as the arch/hmm/
        # supervised adapters). `refit_every=1` (the default) refits every
        # bar -- byte-identical to the pre-refit_every behavior. The z-score
        # itself is still recomputed every bar over the current window.
        self._bars_since_fit += 1
        if self._hedge_ratio is None or self._bars_since_fit >= self._refit_every:
            self._bars_since_fit = 0
            design = self._sm.add_constant(x)  # type: ignore[attr-defined]
            fit = self._sm.OLS(y, design).fit()  # type: ignore[attr-defined]
            self._hedge_ratio = float(fit.params[1])
        hedge_ratio = self._hedge_ratio
        spread = y - hedge_ratio * x
        std = float(np.std(spread))
        if std == 0:
            return []
        z = (spread[-1] - float(np.mean(spread))) / std

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
                reason=f"{self.name}: spread z={z:.2f}, hedge_ratio={hedge_ratio:.4f}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
