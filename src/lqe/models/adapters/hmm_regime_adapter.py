"""`HmmRegimeAdapter` (docs/03 §3.2, family: regime). `hmmlearn` (BSD-3) is
kept in the optional `models` extra, not the base runtime — imported lazily
so a base install never needs it, and a missing install quarantines cleanly
at intake instead of crashing.

Fits a 2-state Gaussian HMM on the trailing return series every
`refit_every` bars (seeded → deterministic), infers the current hidden
state, and goes long only in the higher-mean-return ("risk-on") regime,
flat in the other. A regime read, not a price target.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


def _import_hmm() -> object:
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError as exc:
        raise ImportError(
            "HmmRegimeAdapter requires the optional 'models' extra: pip install '.[models]'"
        ) from exc
    return GaussianHMM


class HmmRegimeAdapter:
    def __init__(
        self, *, symbol: Symbol, name: str, window: int = 120, refit_every: int = 20, seed: int = 0
    ) -> None:
        self._hmm_cls = _import_hmm()
        self.name = name
        self.params: dict[str, object] = {
            "window": window, "refit_every": refit_every, "seed": seed,
        }
        self._symbol = symbol
        self._window = window
        self._refit_every = refit_every
        self._seed = seed
        self._closes: list[float] = []
        self._position: Literal["FLAT", "LONG"] = "FLAT"
        self._bars_since_fit = 0
        self._risk_on_state: int | None = None
        self._model: object = None

    def on_start(self, ctx: Context) -> None:
        self._closes.clear()
        self._bars_since_fit = 0
        self._risk_on_state = None
        self._model = None
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        self._closes.append(float(ev.c))
        if len(self._closes) < self._window + 1:
            return []

        self._bars_since_fit += 1
        returns = np.diff(np.array(self._closes[-(self._window + 1) :])).reshape(-1, 1)
        if self._model is None or self._bars_since_fit >= self._refit_every:
            self._bars_since_fit = 0
            model = self._hmm_cls(  # type: ignore[operator]
                n_components=2, covariance_type="diag", n_iter=50, random_state=self._seed
            )
            model.fit(returns)
            means = model.means_.ravel()
            self._risk_on_state = int(np.argmax(means))
            self._model = model

        assert self._model is not None
        current_state = int(self._model.predict(returns)[-1])  # type: ignore[attr-defined]
        target: Literal["LONG", "FLAT"] = "LONG" if current_state == self._risk_on_state else "FLAT"
        if target == self._position:
            return []

        self._position = target
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction=target,
                strength=1.0 if target == "LONG" else 0.0,
                intent_kind="ENTER" if target == "LONG" else "EXIT", bar_ts=ev.ts_open,
                reason=f"{self.name}: hmm state={current_state} (risk_on={self._risk_on_state})",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
