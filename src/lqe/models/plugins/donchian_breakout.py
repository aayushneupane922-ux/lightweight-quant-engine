"""Donchian channel breakout (docs/03 §3.3's own worked example, family:
trend). Long on a close at/above the N-bar high, flat on a close at/below
the N-bar low.
"""

from __future__ import annotations

from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.manifest import DataNeeds, ModelManifest

MANIFEST = ModelManifest(
    id="donchian_breakout",
    family="trend",
    sleeve="trend_momentum",
    one_liner="Enter when price clears the N-bar channel.",
    economic_rationale="Breakouts can extend when order flow is one-sided.",
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={"lookback": "int>1"},
    failure_modes=["false breakouts in range regimes"],
)


def make_strategy(symbol: Symbol) -> IndicatorRuleAdapter:
    return IndicatorRuleAdapter(
        symbol=symbol,
        preset="donchian_breakout",
        name=MANIFEST.id,
        params={"lookback": 20.0},
    )
