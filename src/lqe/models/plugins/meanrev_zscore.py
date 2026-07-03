"""Z-score mean-reversion (docs/03 family: mean_reversion). Long when price
is far enough below its rolling mean (a deep z-score dip), flat once it
reverts back up to the exit z-score.
"""

from __future__ import annotations

from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.manifest import DataNeeds, ModelManifest

MANIFEST = ModelManifest(
    id="meanrev_zscore",
    family="mean_reversion",
    one_liner="Long on a deep rolling z-score dip, flat once it reverts.",
    economic_rationale=(
        "Prices oscillate around a local mean absent a regime change; a large "
        "deviation is more likely to revert than extend further."
    ),
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={"window": "int>1", "entry_z": "float<0", "exit_z": "float"},
    failure_modes=["trending/regime-break markets never revert, causing sustained losses"],
)


def make_strategy(symbol: Symbol) -> IndicatorRuleAdapter:
    return IndicatorRuleAdapter(
        symbol=symbol,
        preset="zscore_reversion",
        name=MANIFEST.id,
        params={"window": 20.0, "entry_z": -2.0, "exit_z": 0.0},
    )
