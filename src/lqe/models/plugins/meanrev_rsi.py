"""RSI fade (docs/03 family: mean_reversion). Long once RSI is oversold,
flat once it becomes overbought.
"""

from __future__ import annotations

from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.manifest import DataNeeds, ModelManifest

MANIFEST = ModelManifest(
    id="meanrev_rsi",
    family="mean_reversion",
    one_liner="Long once RSI is oversold, flat once RSI is overbought.",
    economic_rationale="An oversold reading reflects overextended selling likely to mean-revert.",
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={"window": "int>1", "oversold": "float", "overbought": "float"},
    failure_modes=["RSI can stay oversold for extended periods in a strong downtrend"],
)


def make_strategy(symbol: Symbol) -> IndicatorRuleAdapter:
    return IndicatorRuleAdapter(
        symbol=symbol,
        preset="rsi_fade",
        name=MANIFEST.id,
        params={"window": 14.0, "oversold": 30.0, "overbought": 70.0},
    )
