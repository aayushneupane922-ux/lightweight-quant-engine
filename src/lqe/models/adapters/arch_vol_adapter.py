"""`ArchVolAdapter` (docs/03 §3.3, family: volatility). `arch` (NCSA) is
kept in the optional `models` extra, not the base runtime — imported
lazily so a base install never needs it, and a missing install quarantines
cleanly at intake instead of crashing.

Fits a GARCH(1,1) on the trailing return series every `refit_every` bars
(a full refit every bar would be needlessly slow and noisy) and forecasts
one bar ahead. Long while forecast volatility sits below its own trailing
median (a calmer regime, favorable for holding exposure), flat once it
rises back above it (an expanding, riskier regime).
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from lqe.constants import ADAPTER_HISTORY_CAP
from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


def _import_arch_model() -> object:
    try:
        from arch import arch_model
    except ImportError as exc:
        raise ImportError(
            "ArchVolAdapter requires the optional 'models' extra: pip install '.[models]'"
        ) from exc
    return arch_model


class ArchVolAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        window: int = 120,
        refit_every: int = 10,
    ) -> None:
        self._arch_model = _import_arch_model()
        self.name = name
        self.params: dict[str, object] = {"window": window, "refit_every": refit_every}
        self._symbol = symbol
        self._window = window
        self._refit_every = refit_every
        self._closes: list[float] = []
        self._forecast_history: list[float] = []
        self._position: Literal["FLAT", "LONG"] = "FLAT"
        self._bars_since_fit = 0

    def on_start(self, ctx: Context) -> None:
        self._closes.clear()
        self._forecast_history.clear()
        self._bars_since_fit = 0
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        self._closes.append(float(ev.c))
        # bound raw history (perf phase 3c) -- all reads are [-window:] tails
        if len(self._closes) > 2 * ADAPTER_HISTORY_CAP:
            del self._closes[: -ADAPTER_HISTORY_CAP]
        if len(self._closes) < self._window + 1:
            return []

        self._bars_since_fit += 1
        if self._bars_since_fit < self._refit_every and self._forecast_history:
            forecast_vol = self._forecast_history[-1]
        else:
            self._bars_since_fit = 0
            tail = np.array(self._closes[-(self._window + 1) :])
            returns = 100.0 * np.diff(tail) / tail[:-1]
            model = self._arch_model(returns, vol="Garch", p=1, q=1)  # type: ignore[operator]
            fit = model.fit(disp="off")
            forecast = fit.forecast(horizon=1)
            forecast_vol = float(np.sqrt(forecast.variance.to_numpy()[-1, 0]))
            self._forecast_history.append(forecast_vol)

        if len(self._forecast_history) < 5:
            return []
        baseline = float(np.median(self._forecast_history))
        target: Literal["LONG", "FLAT"] = "LONG" if forecast_vol < baseline else "FLAT"
        if target == self._position:
            return []

        self._position = target
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction=target,
                strength=1.0 if target == "LONG" else 0.0,
                intent_kind="ENTER" if target == "LONG" else "EXIT", bar_ts=ev.ts_open,
                reason=f"{self.name}: forecast_vol={forecast_vol:.4f} vs baseline={baseline:.4f}",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
