"""MACD trend-follower (docs/03 family: trend). Long while the MACD line
sits above its own signal line, flat otherwise.
"""

from __future__ import annotations

from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.manifest import DataNeeds, ModelManifest

MANIFEST = ModelManifest(
    id="trend_macd_cross",
    family="trend",
    sleeve="trend_momentum",
    one_liner="Long while MACD is above its signal line, flat otherwise.",
    economic_rationale=(
        "Trend-following: momentum tends to persist past the point where "
        "fast/slow moving averages converge."
    ),
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={"fast": "int>1", "slow": "int>fast", "signal": "int>1"},
    failure_modes=["whipsaws in choppy/sideways markets", "lag at trend reversals"],
)


def make_strategy(symbol: Symbol) -> IndicatorRuleAdapter:
    return IndicatorRuleAdapter(
        symbol=symbol,
        preset="macd_trend",
        name=MANIFEST.id,
        params={"fast": 12.0, "slow": 26.0, "signal": 9.0},
    )
