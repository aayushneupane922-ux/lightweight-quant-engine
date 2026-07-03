"""`SearchableModel`: a catalog model paired with the numeric search space
the loop explores and a parametrized builder (docs/11 §11.6). The M6 catalog
plugins expose fixed-param `make_strategy(symbol)` factories; searching needs
to *vary* those params, so this is the seam that turns a manifest + a
param-set into a concrete `Strategy`.

The default set is intentionally small and diverse (one per family) — M8
proves the loop mechanics; M11 scales the searchable surface. Ranges here are
the rule-based hypothesizer's defaults; M9's LLM may propose others.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lqe.autonomy.optimizer import ParamRange, SearchSpace
from lqe.core.types import Symbol
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.base import Strategy
from lqe.models.plugins.trend_ma_cross import TrendMaCross

StrategyBuilder = Callable[[Symbol, dict[str, Any]], Strategy]


@dataclass(frozen=True)
class SearchableModel:
    model_id: str
    family: str
    space: SearchSpace
    build: StrategyBuilder


def build_ma_cross(symbol: Symbol, params: dict[str, Any]) -> Strategy:
    # TrendMaCross enforces fast < slow (raises otherwise); the objective
    # catches that and scores the invalid point badly so Optuna avoids it.
    return TrendMaCross(symbol=symbol, fast=int(params["fast"]), slow=int(params["slow"]))


def build_preset(preset: str, model_id: str) -> StrategyBuilder:
    def build(symbol: Symbol, params: dict[str, Any]) -> Strategy:
        return IndicatorRuleAdapter(
            symbol=symbol,
            preset=preset,
            name=model_id,
            params={k: float(v) for k, v in params.items()},
        )

    return build


def default_searchable_models() -> list[SearchableModel]:
    return [
        SearchableModel(
            model_id="trend_ma_cross",
            family="trend",
            space=SearchSpace(
                model_id="trend_ma_cross",
                ranges={
                    "fast": ParamRange(low=2, high=20, is_int=True),
                    "slow": ParamRange(low=21, high=80, is_int=True),
                },
            ),
            build=build_ma_cross,
        ),
        SearchableModel(
            model_id="momentum_tsmom",
            family="momentum",
            space=SearchSpace(
                model_id="momentum_tsmom",
                ranges={"lookback": ParamRange(low=10, high=120, is_int=True)},
            ),
            build=build_preset("tsmom", "momentum_tsmom"),
        ),
        SearchableModel(
            model_id="meanrev_rsi",
            family="mean_reversion",
            space=SearchSpace(
                model_id="meanrev_rsi",
                ranges={"window": ParamRange(low=5, high=30, is_int=True)},
            ),
            build=build_preset("rsi_fade", "meanrev_rsi"),
        ),
    ]
