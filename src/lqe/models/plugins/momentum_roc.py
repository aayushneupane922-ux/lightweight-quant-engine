"""Rate-of-change momentum (docs/03 family: momentum). Long once the N-bar
rate of change clears a threshold, flat once it drops back to/below zero.
"""

from __future__ import annotations

from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.manifest import DataNeeds, ModelManifest

MANIFEST = ModelManifest(
    id="momentum_roc",
    family="momentum",
    sleeve="trend_momentum",
    one_liner="Long once N-bar rate-of-change clears a threshold, flat at/below zero.",
    economic_rationale="Accelerating price change can signal a fresh momentum regime starting.",
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={"lookback": "int>1", "threshold": "float"},
    failure_modes=["whipsaws around the zero-crossing in low-momentum regimes"],
)


def make_strategy(symbol: Symbol) -> IndicatorRuleAdapter:
    return IndicatorRuleAdapter(
        symbol=symbol,
        preset="roc_momentum",
        name=MANIFEST.id,
        params={"lookback": 20.0, "threshold": 0.0},
    )
