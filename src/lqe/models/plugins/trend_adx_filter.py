"""MA-cross gated by ADX trend strength (docs/03 family: trend). Only takes
the fast/slow SMA cross signal when ADX confirms the market is actually
trending; stands aside in choppy regimes regardless of MA position.
"""

from __future__ import annotations

from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.manifest import DataNeeds, ModelManifest

MANIFEST = ModelManifest(
    id="trend_adx_filter",
    family="trend",
    sleeve="trend_momentum",
    one_liner="MA cross, but only acted on when ADX confirms a real trend.",
    economic_rationale=(
        "MA crosses are noisy in choppy regimes; gating on trend strength (ADX) "
        "should filter out the weakest signals."
    ),
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={
        "fast": "int>1", "slow": "int>fast", "adx_window": "int>1", "adx_threshold": "float>0",
    },
    failure_modes=["misses early-trend entries while ADX is still catching up"],
)


def make_strategy(symbol: Symbol) -> IndicatorRuleAdapter:
    return IndicatorRuleAdapter(
        symbol=symbol,
        preset="adx_trend",
        name=MANIFEST.id,
        params={"fast": 10.0, "slow": 30.0, "adx_window": 14.0, "adx_threshold": 25.0},
    )
