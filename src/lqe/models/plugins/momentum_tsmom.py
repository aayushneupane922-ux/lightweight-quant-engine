"""Time-series momentum (docs/03 family: momentum). Long when the trailing
N-bar return is positive, flat otherwise — the classic single-instrument
TSMOM signal (Moskowitz/Ooi/Pedersen).
"""

from __future__ import annotations

from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.manifest import DataNeeds, ModelManifest

MANIFEST = ModelManifest(
    id="momentum_tsmom",
    family="momentum",
    one_liner="Long when trailing N-bar return is positive, flat otherwise.",
    economic_rationale=(
        "Time-series momentum: assets that have trended tend to keep trending "
        "over medium horizons."
    ),
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={"lookback": "int>1"},
    failure_modes=["sharp reversals after an extended run", "sideways chop"],
)


def make_strategy(symbol: Symbol) -> IndicatorRuleAdapter:
    return IndicatorRuleAdapter(
        symbol=symbol,
        preset="tsmom",
        name=MANIFEST.id,
        params={"lookback": 90.0},
    )
