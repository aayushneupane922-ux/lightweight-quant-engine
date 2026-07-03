"""Volatility-expansion breakout (docs/03 family: volatility). Long once
realized volatility expands well past its recent baseline (a regime shift
into a more active market), flat once it contracts back to/below baseline.
"""

from __future__ import annotations

from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.manifest import DataNeeds, ModelManifest

MANIFEST = ModelManifest(
    id="vol_breakout",
    family="volatility",
    one_liner="Long once realized vol expands past baseline, flat once it contracts back.",
    economic_rationale=(
        "A volatility regime shift often accompanies a directional move as new "
        "information gets priced in."
    ),
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={"window": "int>1", "expansion_ratio": "float>1"},
    failure_modes=["vol spikes that are pure noise/mean-reverting with no directional edge"],
)


def make_strategy(symbol: Symbol) -> IndicatorRuleAdapter:
    return IndicatorRuleAdapter(
        symbol=symbol,
        preset="vol_breakout",
        name=MANIFEST.id,
        params={"window": 20.0, "expansion_ratio": 1.5},
    )
