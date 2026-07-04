"""The scaled catalog (docs/10 M11, docs/03 §3.1/§3.5): 50+ models reached
by **config, not per-model files** — "one adapter unlocks a whole family."

Native `IndicatorRuleAdapter` presets × sensible parameter grids give a
broad, always-constructible surface (numpy-only, "own" licence). The
heavy-lib adapters (pairs/GARCH/HMM/change-point/portfolio/risk/supervised)
are registered too; when the optional `models` extra isn't installed they
quarantine *transparently* with the ImportError as the reason (docs/03
§3.4) — visible, never silently dropped.

Honesty rails (docs/03 §3.6): every model enters `unproven` and can only be
ranked `validated` by a gate PASS; the deliberately-weak `naive_always_long`
control is kept so the tooling visibly rejects things; DSR/PBO trial-
counting spans this whole surface (M8's registry, F2).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from lqe.core.types import Symbol
from lqe.models.adapters._portfolio_projection import StaticWeightProjectionAdapter, WeightFn
from lqe.models.adapters.arch_vol_adapter import ArchVolAdapter
from lqe.models.adapters.changepoint_adapter import ChangePointAdapter
from lqe.models.adapters.hmm_regime_adapter import HmmRegimeAdapter
from lqe.models.adapters.indicator_rule_adapter import IndicatorRuleAdapter
from lqe.models.adapters.pypfopt_adapter import PyPortfolioOptAdapter
from lqe.models.adapters.riskfolio_adapter import RiskfolioAdapter
from lqe.models.adapters.skfolio_adapter import SkfolioOptimizerAdapter
from lqe.models.adapters.statsmodels_pairs_adapter import StatsmodelsPairsAdapter
from lqe.models.adapters.supervised_signal_adapter import SupervisedSignalAdapter
from lqe.models.base import Strategy
from lqe.models.catalog import IntakeResult, ModelCatalog
from lqe.models.manifest import DataNeeds, Family, ModelManifest, Sleeve
from lqe.models.plugins import naive_always_long, trend_ma_cross

# (preset, family, sleeve, one_liner) for the native indicator presets.
# docs/14 §2 (v4): `sleeve` is the return-driver grouping the diversification
# score measures against -- coarser than `family` (e.g. "trend" and
# "momentum" are both sleeve `trend_momentum`, since they're expected to be
# highly correlated and count as ~1 effective bet, per docs/14's own sleeve A).
_PRESET_META: dict[str, tuple[Family, Sleeve, str]] = {
    "macd_trend": ("trend", "trend_momentum", "Long while MACD is above its signal line."),
    "donchian_breakout": (
        "trend", "trend_momentum", "Enter when price clears the N-bar channel."
    ),
    "adx_trend": ("trend", "trend_momentum", "MA cross gated by ADX trend strength."),
    "tsmom": ("momentum", "trend_momentum", "Long when trailing N-bar return is positive."),
    "roc_momentum": (
        "momentum", "trend_momentum", "Long once N-bar rate-of-change clears a threshold."
    ),
    "zscore_reversion": (
        "mean_reversion", "mean_reversion", "Long on a deep rolling z-score dip."
    ),
    "bollinger_fade": (
        "mean_reversion", "mean_reversion", "Long on a lower-band touch, flat at the midline."
    ),
    "rsi_fade": ("mean_reversion", "mean_reversion", "Long once RSI is oversold."),
    "vol_breakout": ("volatility", "volatility", "Long once realized vol expands past baseline."),
    # docs/14 (v4) M23: sleeve additions on existing spot data -- no new
    # data prerequisite, per docs/14 §5's "no new data" sleeve list.
    "keltner_reversion": (
        "mean_reversion", "mean_reversion", "Long on an ATR-channel dip, flat at the midline."
    ),
    "ou_fairvalue": (
        "mean_reversion", "mean_reversion",
        "Long on a deep EMA fair-value deviation, flat once it reverts.",
    ),
    "vol_mean_reversion": (
        "volatility", "volatility", "Long on a vol spike, flat once it normalizes."
    ),
    "vol_regime_gate": (
        "regime", "regime_overlay", "Long in a calm-vol regime, flat once it turns turbulent."
    ),
    "opening_range_breakout": (
        "trend", "breakout_structure", "Long on a break above today's opening range."
    ),
    "support_resistance_range": (
        "mean_reversion", "breakout_structure", "Long near range support, flat near resistance."
    ),
    "squeeze_breakout": (
        "trend", "breakout_structure", "Long when a genuine Bollinger squeeze resolves upward."
    ),
    "time_of_day": (
        "trend", "seasonality", "Long only during a declared UTC hour window."
    ),
    "day_of_week": (
        "trend", "seasonality", "Long on weekdays, flat over the weekend."
    ),
    "turn_of_month": (
        "trend", "seasonality", "Long near the calendar month boundary, flat mid-month."
    ),
}

# preset -> list of parameter dicts to enumerate (each becomes one model).
_PRESET_GRID: dict[str, list[dict[str, float]]] = {
    "macd_trend": [
        {"fast": 12, "slow": 26, "signal": 9},
        {"fast": 8, "slow": 21, "signal": 5},
        {"fast": 16, "slow": 32, "signal": 9},
    ],
    "donchian_breakout": [{"lookback": lb} for lb in (10, 20, 40, 55, 80)],
    "adx_trend": [
        {"fast": 10, "slow": 30, "adx_threshold": 25},
        {"fast": 5, "slow": 20, "adx_threshold": 20},
        {"fast": 20, "slow": 50, "adx_threshold": 30},
        {"fast": 12, "slow": 40, "adx_threshold": 22},
    ],
    "tsmom": [{"lookback": lb} for lb in (30, 60, 90, 120, 150)],
    "roc_momentum": [{"lookback": lb} for lb in (10, 20, 40, 60, 90)],
    "zscore_reversion": [
        {"window": 15, "entry_z": -2.0}, {"window": 20, "entry_z": -2.0},
        {"window": 20, "entry_z": -2.5}, {"window": 30, "entry_z": -1.5},
    ],
    "bollinger_fade": [
        {"window": 20, "n_std": 2.0}, {"window": 20, "n_std": 2.5}, {"window": 30, "n_std": 2.0},
    ],
    "rsi_fade": [
        {"window": 14, "oversold": 30, "overbought": 70},
        {"window": 10, "oversold": 25, "overbought": 75},
        {"window": 20, "oversold": 35, "overbought": 65},
    ],
    "vol_breakout": [
        {"window": 20, "expansion_ratio": 1.5}, {"window": 30, "expansion_ratio": 1.5},
        {"window": 20, "expansion_ratio": 2.0}, {"window": 40, "expansion_ratio": 1.5},
    ],
    "keltner_reversion": [
        {"window": 20, "n_atr": 2.0}, {"window": 20, "n_atr": 2.5}, {"window": 30, "n_atr": 2.0},
    ],
    "ou_fairvalue": [
        {"window": 40, "entry_z": -1.5, "exit_z": 0.0},
        {"window": 60, "entry_z": -1.5, "exit_z": 0.0},
        {"window": 60, "entry_z": -2.0, "exit_z": 0.0},
    ],
    "vol_mean_reversion": [
        {"window": 20, "spike_ratio": 1.5}, {"window": 30, "spike_ratio": 1.5},
        {"window": 20, "spike_ratio": 2.0},
    ],
    "vol_regime_gate": [
        {"window": 20, "calm_ratio": 1.2}, {"window": 30, "calm_ratio": 1.2},
        {"window": 20, "calm_ratio": 1.5},
    ],
    "opening_range_breakout": [{"or_bars": ob} for ob in (15, 30, 60)],
    "support_resistance_range": [{"lookback": lb} for lb in (20, 40, 55)],
    "squeeze_breakout": [
        {"window": 20, "n_std": 2.0, "squeeze_lookback": 60},
        {"window": 20, "n_std": 2.5, "squeeze_lookback": 60},
        {"window": 30, "n_std": 2.0, "squeeze_lookback": 90},
    ],
    "time_of_day": [
        {"start_hour": 13, "end_hour": 21}, {"start_hour": 0, "end_hour": 8},
        {"start_hour": 8, "end_hour": 16},
    ],
    "day_of_week": [{}],
    "turn_of_month": [{"window_days": wd} for wd in (2, 3, 5)],
}


def _native_manifest(
    model_id: str, family: Family, sleeve: Sleeve, one_liner: str
) -> ModelManifest:
    return ModelManifest(
        id=model_id, family=family, sleeve=sleeve, one_liner=one_liner,
        economic_rationale=(
            "A config of a vetted native indicator rule; the gate judges it, not breadth."
        ),
        data_needs=DataNeeds(instruments=1, kind="OHLCV"), oss_libs=["own"],
        params_schema={},
        failure_modes=["regime mismatch; overfitting if promoted without the gate"],
    )


def _heavy_manifest(
    model_id: str, family: Family, sleeve: Sleeve, one_liner: str, lib: str
) -> ModelManifest:
    return ModelManifest(
        id=model_id, family=family, sleeve=sleeve, one_liner=one_liner,
        economic_rationale=(
            f"Advanced statistical model via {lib}; unproven until the gate passes it."
        ),
        data_needs=DataNeeds(instruments=1, kind="OHLCV"), oss_libs=[lib],
        params_schema={},
        failure_modes=["requires the optional 'models' extra; overfitting risk"],
    )


def _native_entries(symbol: Symbol) -> list[tuple[ModelManifest, Callable[[], Strategy]]]:
    entries: list[tuple[ModelManifest, Callable[[], Strategy]]] = []
    for preset, grid in _PRESET_GRID.items():
        family, sleeve, one_liner = _PRESET_META[preset]
        for i, params in enumerate(grid):
            model_id = f"{preset}_{i}"
            entries.append(
                (
                    _native_manifest(model_id, family, sleeve, one_liner),
                    _native_factory(symbol, preset, model_id, params),
                )
            )
    # a few MA-cross configs + the reference model + the weak control
    for fast, slow in ((5, 20), (10, 30), (20, 60), (10, 50)):
        mid = f"trend_ma_cross_{fast}_{slow}"
        entries.append(
            (
                _native_manifest(mid, "trend", "trend_momentum", "Fast/slow SMA cross."),
                _ma_cross_factory(symbol, mid, fast, slow),
            )
        )
    entries.append((trend_ma_cross.MANIFEST, lambda: trend_ma_cross.make_strategy(symbol)))
    entries.append((naive_always_long.MANIFEST, lambda: naive_always_long.make_strategy(symbol)))
    return entries


def _native_factory(
    symbol: Symbol, preset: str, model_id: str, params: dict[str, float]
) -> Callable[[], Strategy]:
    return lambda: IndicatorRuleAdapter(symbol=symbol, preset=preset, name=model_id, params=params)


def _ma_cross_factory(
    symbol: Symbol, model_id: str, fast: int, slow: int
) -> Callable[[], Strategy]:
    return lambda: trend_ma_cross.TrendMaCross(symbol=symbol, fast=fast, slow=slow)


def _synthetic_universe(symbol: Symbol) -> dict[str, list[float]]:
    # 3 assets, not 2: skfolio's HierarchicalRiskParity computes an "optimal
    # number of clusters" via a gap statistic that needs >=3 assets to have
    # any candidate cluster count to search over; with exactly 2 it raises
    # (`argmax of an empty sequence`) regardless of how much history is
    # given. This path was never actually exercised before docs/12 M13
    # installed skfolio/PyPortfolioOpt/riskfolio-lib -- all 3 were quarantined
    # until then, so the 2-asset universe's HRP incompatibility was latent.
    return {
        symbol: [1.0, 2.0, 3.0, 4.0], "ETH-USDT": [1.0, 1.1, 1.2, 1.3],
        "SOL-USDT": [1.0, 0.95, 1.05, 1.0],
    }


def _inverse_vol_weights(universe: Mapping[str, Sequence[float]]) -> Mapping[str, float]:
    # docs/14 sleeve M: inverse-volatility weighting -- a native (numpy-only)
    # allocator needing no heavy lib, unlike the cvxpy-based optimizers above.
    inv_vol = {}
    for sym, closes in universe.items():
        returns = np.diff(np.log(np.asarray(closes, dtype=np.float64)))
        std = float(np.std(returns))
        inv_vol[sym] = 1.0 / std if std > 0 else 0.0
    total = sum(inv_vol.values())
    if total <= 0:
        n = len(universe)
        return dict.fromkeys(universe, 1.0 / n)
    return {sym: weight / total for sym, weight in inv_vol.items()}


def _min_variance_weights(universe: Mapping[str, Sequence[float]]) -> Mapping[str, float]:
    # docs/14 sleeve M: the closed-form unconstrained global-minimum-variance
    # portfolio (w = Sigma^-1 * 1 / (1' Sigma^-1 1)) -- a native (numpy-only)
    # allocator; honestly declared unconstrained (a real weight can come out
    # negative/short if the sample covariance calls for it), unlike the
    # long-only cvxpy-based optimizers above.
    symbols = list(universe.keys())
    returns = np.array(
        [np.diff(np.log(np.asarray(universe[sym], dtype=np.float64))) for sym in symbols]
    )
    cov = np.cov(returns)
    try:
        inv_cov = np.linalg.inv(np.atleast_2d(cov))
    except np.linalg.LinAlgError:
        n = len(symbols)
        return dict.fromkeys(symbols, 1.0 / n)
    ones = np.ones(len(symbols))
    denom = float(ones @ inv_cov @ ones)
    if denom == 0:
        n = len(symbols)
        return dict.fromkeys(symbols, 1.0 / n)
    weights = (inv_cov @ ones) / denom
    return dict(zip(symbols, weights.tolist(), strict=True))


def _native_allocator_entries(symbol: Symbol) -> list[tuple[ModelManifest, Callable[[], Strategy]]]:
    universe = _synthetic_universe(symbol)
    specs: list[tuple[str, str, WeightFn]] = [
        ("alloc_inverse_vol", "Inverse-volatility weight.", _inverse_vol_weights),
        (
            "alloc_min_variance", "Unconstrained global-minimum-variance weight.",
            _min_variance_weights,
        ),
    ]

    def make_factory(mid: str, fn: WeightFn) -> Callable[[], Strategy]:
        # `mid`/`fn` are bound as this closure's own arguments, not looked
        # up from the loop below at call time -- avoids the classic Python
        # late-binding-closure bug where every factory would otherwise see
        # whatever `model_id`/`weight_fn` the loop last left behind.
        return lambda: StaticWeightProjectionAdapter(
            symbol=symbol, name=mid, universe_closes=universe, weight_fn=fn
        )

    entries: list[tuple[ModelManifest, Callable[[], Strategy]]] = []
    for model_id, one_liner, weight_fn in specs:
        manifest = _native_manifest(model_id, "portfolio", "allocator", one_liner)
        entries.append((manifest, make_factory(model_id, weight_fn)))
    return entries


def _heavy_entries(symbol: Symbol) -> list[tuple[ModelManifest, Callable[[], Strategy]]]:
    universe = _synthetic_universe(symbol)
    hedge = [10.0, 10.5, 10.2, 10.8]

    def factory(cls: Any, **kw: Any) -> Callable[[], Strategy]:
        return lambda: cls(symbol=symbol, **kw)

    # (id, family, sleeve, one_liner, lib, factory)
    specs: list[tuple[str, Family, Sleeve, str, str, Callable[[], Strategy]]] = [
        ("pairs_ols", "pairs", "stat_arb", "OLS-hedge spread reversion.", "statsmodels",
         factory(StatsmodelsPairsAdapter, name="pairs_ols", hedge_closes=hedge)),
        ("vol_garch", "volatility", "volatility", "GARCH(1,1) vol-regime filter.", "arch",
         factory(ArchVolAdapter, name="vol_garch")),
        ("regime_hmm", "regime", "regime_overlay", "2-state Gaussian HMM regime switch.",
         "hmmlearn", factory(HmmRegimeAdapter, name="regime_hmm")),
        ("regime_changepoint", "regime", "regime_overlay", "Change-point segment regime.",
         "ruptures", factory(ChangePointAdapter, name="regime_changepoint")),
        ("portfolio_mvo", "portfolio", "allocator", "Max-Sharpe mean-variance weight.",
         "PyPortfolioOpt",
         factory(PyPortfolioOptAdapter, name="portfolio_mvo", universe_closes=universe)),
        ("portfolio_hrp", "portfolio", "allocator", "Hierarchical risk parity weight.",
         "skfolio",
         factory(SkfolioOptimizerAdapter, name="portfolio_hrp", universe_closes=universe)),
        ("riskalloc_rp", "risk_allocation", "allocator", "Risk-parity allocation.",
         "riskfolio-lib",
         factory(RiskfolioAdapter, name="riskalloc_rp", universe_closes=universe)),
        ("supervised_logit", "supervised", "ml_signal", "Logistic next-bar direction (gated).",
         "scikit-learn",
         factory(SupervisedSignalAdapter, name="supervised_logit", kind="logistic")),
        ("supervised_gbm", "supervised", "ml_signal", "Gradient-boosted direction (gated).",
         "lightgbm",
         factory(SupervisedSignalAdapter, name="supervised_gbm", kind="gbm")),
    ]
    return [
        (_heavy_manifest(mid, family, sleeve, one_liner, lib), build)
        for mid, family, sleeve, one_liner, lib, build in specs
    ]


def build_scaled_catalog(symbol: Symbol) -> tuple[ModelCatalog, list[IntakeResult]]:
    """Register the full scaled catalog for `symbol`. Native models admit;
    heavy-lib models admit only if the `models` extra is installed, else
    quarantine transparently. Returns the catalog + the intake result for
    each so callers can see exactly why any model was held back."""
    catalog = ModelCatalog()
    results = [
        catalog.register(manifest, factory)
        for manifest, factory in (
            *_native_entries(symbol), *_native_allocator_entries(symbol), *_heavy_entries(symbol)
        )
    ]
    return catalog, results
