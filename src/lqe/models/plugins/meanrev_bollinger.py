"""Bollinger Band fade (docs/03 family: mean_reversion). Long on a touch of
the lower band, flat once price fades back up to the midline.
"""

from __future__ import annotations

from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.manifest import DataNeeds, ModelManifest

MANIFEST = ModelManifest(
    id="meanrev_bollinger",
    family="mean_reversion",
    one_liner="Long on a lower-band touch, flat back at the midline.",
    economic_rationale="A close outside a volatility band is a statistical extreme likely to fade.",
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={"window": "int>1", "n_std": "float>0"},
    failure_modes=["band walks during a strong trend, generating repeated losing entries"],
)


def make_strategy(symbol: Symbol) -> IndicatorRuleAdapter:
    return IndicatorRuleAdapter(
        symbol=symbol,
        preset="bollinger_fade",
        name=MANIFEST.id,
        params={"window": 20.0, "n_std": 2.0},
    )
