"""A much broader searchable surface (post-v1.0 extension, user-requested —
see HANDOFF.md / COMPONENT-GUIDE.md): one `SearchableModel` per native
indicator preset in `models.catalog_scale` (the same 9 presets ×
param-grids that give the scaled catalog its native breadth), spanning all 4
native families, plus the reference `trend_ma_cross`. 10 searchable models
total, versus the 3-model M8 proving set
(`autonomy.searchable.default_searchable_models`, still the default for a
one-shot `lqe autopilot` run — this module is additive, not a replacement).

The 3 cvxpy portfolio optimizers and the statistical/ML adapters (pairs,
HMM regime, change-point, supervised, GARCH-vol) trade live in the fleet —
every admitted catalog model does — but aren't wired into Optuna's numeric
search here: their parameter spaces don't map onto a scalar `ParamRange`
sweep the way an indicator threshold does. Making them searchable would be
a separate, per-adapter change, not a broadening of this module.

Range bounds are a superset of each preset's `_PRESET_GRID` sample points in
`catalog_scale.py` (so Optuna explores at least as widely as the fixed grid
already proves works), not re-derived from anywhere else.
"""

from __future__ import annotations

from lqe.autonomy.optimizer import ParamRange, SearchSpace
from lqe.autonomy.searchable import SearchableModel, build_ma_cross, build_preset

_RANGES: dict[str, dict[str, ParamRange]] = {
    "macd_trend": {
        "fast": ParamRange(low=5, high=20, is_int=True),
        "slow": ParamRange(low=21, high=40, is_int=True),
        "signal": ParamRange(low=4, high=12, is_int=True),
    },
    "donchian_breakout": {"lookback": ParamRange(low=10, high=80, is_int=True)},
    "adx_trend": {
        "fast": ParamRange(low=5, high=20, is_int=True),
        "slow": ParamRange(low=20, high=50, is_int=True),
        "adx_threshold": ParamRange(low=15, high=35, is_int=False),
    },
    "tsmom": {"lookback": ParamRange(low=20, high=150, is_int=True)},
    "roc_momentum": {"lookback": ParamRange(low=10, high=90, is_int=True)},
    "zscore_reversion": {
        "window": ParamRange(low=10, high=35, is_int=True),
        "entry_z": ParamRange(low=-3.0, high=-1.0, is_int=False),
    },
    "bollinger_fade": {
        "window": ParamRange(low=15, high=35, is_int=True),
        "n_std": ParamRange(low=1.5, high=3.0, is_int=False),
    },
    "rsi_fade": {
        "window": ParamRange(low=5, high=30, is_int=True),
        "oversold": ParamRange(low=20, high=40, is_int=False),
        "overbought": ParamRange(low=60, high=80, is_int=False),
    },
    "vol_breakout": {
        "window": ParamRange(low=15, high=45, is_int=True),
        "expansion_ratio": ParamRange(low=1.2, high=2.5, is_int=False),
    },
}

_FAMILY: dict[str, str] = {
    "macd_trend": "trend",
    "donchian_breakout": "trend",
    "adx_trend": "trend",
    "tsmom": "momentum",
    "roc_momentum": "momentum",
    "zscore_reversion": "mean_reversion",
    "bollinger_fade": "mean_reversion",
    "rsi_fade": "mean_reversion",
    "vol_breakout": "volatility",
}


def broad_searchable_models() -> list[SearchableModel]:
    """One `SearchableModel` per native indicator preset (9) plus the
    reference `trend_ma_cross` (10 total), spanning all 4 native families."""
    models = [
        SearchableModel(
            model_id=preset,
            family=_FAMILY[preset],
            space=SearchSpace(model_id=preset, ranges=ranges),
            build=build_preset(preset, preset),
        )
        for preset, ranges in _RANGES.items()
    ]
    models.append(
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
        )
    )
    return models
