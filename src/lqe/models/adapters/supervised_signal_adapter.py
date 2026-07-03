"""`SupervisedSignalAdapter` (docs/03 §3.2, family: supervised). scikit-learn
(BSD-3) / LightGBM (MIT) are kept in the optional `models` extra, not the
base runtime — imported lazily so a base install never needs it, and a
missing install quarantines cleanly at intake instead of crashing.

A **gated** supervised signal (docs/03 §3.2 "supervised/meta-labeling,
gated"): every `refit_every` bars it fits a classifier on lagged returns to
predict the *next* bar's direction, trained only on data strictly before
the current bar (no look-ahead), seeded for determinism. It goes long on a
predicted up-move, flat otherwise. Like every model it is `unproven` until
the promotion gate says otherwise — ML is not exempt from the gate.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol


def _import_classifier(kind: str) -> Any:
    try:
        if kind == "gbm":
            from lightgbm import LGBMClassifier

            return LGBMClassifier
        from sklearn.linear_model import LogisticRegression

        return LogisticRegression
    except ImportError as exc:
        raise ImportError(
            "SupervisedSignalAdapter requires the optional 'models' extra: pip install '.[models]'"
        ) from exc


class SupervisedSignalAdapter:
    def __init__(
        self,
        *,
        symbol: Symbol,
        name: str,
        lags: int = 5,
        window: int = 200,
        refit_every: int = 25,
        kind: Literal["logistic", "gbm"] = "logistic",
        seed: int = 0,
    ) -> None:
        self._clf_cls = _import_classifier(kind)
        self.name = name
        self.params: dict[str, object] = {
            "lags": lags, "window": window, "refit_every": refit_every, "kind": kind, "seed": seed,
        }
        self._symbol = symbol
        self._lags = lags
        self._window = window
        self._refit_every = refit_every
        self._kind = kind
        self._seed = seed
        self._closes: list[float] = []
        self._position: Literal["FLAT", "LONG"] = "FLAT"
        self._bars_since_fit = 0
        self._model: Any = None

    def on_start(self, ctx: Context) -> None:
        self._closes.clear()
        self._bars_since_fit = 0
        self._model = None
        self._position = "LONG" if ctx.position_qty > 0 else "FLAT"

    def _features_targets(
        self, closes: npt.NDArray[np.float64]
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.int_]]:
        returns = np.diff(closes) / closes[:-1]
        rows, targets = [], []
        # each sample: `lags` past returns -> sign of the NEXT return (label);
        # the final incomplete row (no known next return) is excluded -> no leak
        for i in range(self._lags, len(returns) - 1):
            rows.append(returns[i - self._lags : i])
            targets.append(1 if returns[i + 1] > 0 else 0)
        return np.array(rows), np.array(targets)

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol:
            return []
        self._closes.append(float(ev.c))
        if len(self._closes) < self._window:
            return []

        self._bars_since_fit += 1
        closes = np.array(self._closes[-self._window :])
        if self._model is None or self._bars_since_fit >= self._refit_every:
            self._bars_since_fit = 0
            x, y = self._features_targets(closes)
            if len(np.unique(y)) < 2:
                return []  # degenerate training window; wait
            self._model = self._make_model()
            self._model.fit(x, y)

        returns = np.diff(closes) / closes[:-1]
        latest = returns[-self._lags :].reshape(1, -1)
        pred = int(self._model.predict(latest)[0])
        target: Literal["LONG", "FLAT"] = "LONG" if pred == 1 else "FLAT"
        if target == self._position:
            return []

        self._position = target
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction=target,
                strength=1.0 if target == "LONG" else 0.0,
                intent_kind="ENTER" if target == "LONG" else "EXIT", bar_ts=ev.ts_open,
                reason=f"{self.name}: {self._kind} predicts {'up' if pred else 'down'}",
            )
        ]

    def _make_model(self) -> Any:
        if self._kind == "gbm":
            return self._clf_cls(random_state=self._seed, n_estimators=50, verbose=-1)
        return self._clf_cls(random_state=self._seed, max_iter=200)

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None
