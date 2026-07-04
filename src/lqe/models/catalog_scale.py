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

from collections.abc import Callable
from typing import Any

from lqe.core.types import Symbol
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


def _heavy_entries(symbol: Symbol) -> list[tuple[ModelManifest, Callable[[], Strategy]]]:
    # 3 assets, not 2: skfolio's HierarchicalRiskParity computes an "optimal
    # number of clusters" via a gap statistic that needs >=3 assets to have
    # any candidate cluster count to search over; with exactly 2 it raises
    # (`argmax of an empty sequence`) regardless of how much history is
    # given. This path was never actually exercised before docs/12 M13
    # installed skfolio/PyPortfolioOpt/riskfolio-lib -- all 3 were quarantined
    # until then, so the 2-asset universe's HRP incompatibility was latent.
    universe: dict[str, list[float]] = {
        symbol: [1.0, 2.0, 3.0, 4.0], "ETH-USDT": [1.0, 1.1, 1.2, 1.3],
        "SOL-USDT": [1.0, 0.95, 1.05, 1.0],
    }
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
        for manifest, factory in (*_native_entries(symbol), *_heavy_entries(symbol))
    ]
    return catalog, results
