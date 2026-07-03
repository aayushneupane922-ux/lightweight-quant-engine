"""The default model catalog (docs/10 M6: "ship >=10 concrete models across
the 4 families"). Every plugin module exposes a `MANIFEST` and a
`make_strategy(symbol)` factory; this module is the one place that wires
all of them into a `ModelCatalog`, so registering a new model is exactly
one line here plus one new plugin file (docs/03 §3.7).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from lqe.core.types import Symbol
from lqe.models.base import Strategy
from lqe.models.catalog import IntakeResult, ModelCatalog
from lqe.models.manifest import ModelManifest
from lqe.models.plugins import (
    donchian_breakout,
    meanrev_bollinger,
    meanrev_rsi,
    meanrev_zscore,
    momentum_roc,
    momentum_tsmom,
    naive_always_long,
    trend_adx_filter,
    trend_ma_cross,
    trend_macd_cross,
    vol_breakout,
)

_PLUGINS: tuple[tuple[ModelManifest, Callable[[Symbol], Strategy]], ...] = (
    (trend_ma_cross.MANIFEST, trend_ma_cross.make_strategy),
    (trend_macd_cross.MANIFEST, trend_macd_cross.make_strategy),
    (donchian_breakout.MANIFEST, donchian_breakout.make_strategy),
    (trend_adx_filter.MANIFEST, trend_adx_filter.make_strategy),
    (momentum_tsmom.MANIFEST, momentum_tsmom.make_strategy),
    (momentum_roc.MANIFEST, momentum_roc.make_strategy),
    (meanrev_zscore.MANIFEST, meanrev_zscore.make_strategy),
    (meanrev_bollinger.MANIFEST, meanrev_bollinger.make_strategy),
    (meanrev_rsi.MANIFEST, meanrev_rsi.make_strategy),
    (vol_breakout.MANIFEST, vol_breakout.make_strategy),
    (naive_always_long.MANIFEST, naive_always_long.make_strategy),
)


def build_default_catalog(symbol: Symbol) -> tuple[ModelCatalog, list[IntakeResult]]:
    """Registers every default plugin for `symbol` and returns the catalog
    plus the intake result for each — callers can inspect exactly why any
    model landed in quarantine instead of silently losing that information.
    """
    catalog = ModelCatalog()
    results = []
    for manifest, factory in _PLUGINS:
        bound_factory: Callable[[], Strategy] = partial(factory, symbol)
        results.append(catalog.register(manifest, bound_factory))
    return catalog, results
