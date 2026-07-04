"""docs/03 §3.4 honesty check: the five heavy-lib structural adapters
(statsmodels/arch/PyPortfolioOpt/skfolio/riskfolio-lib) are lazily
imported so the base install never needs them. When the optional
'models'-extra package is *absent*, intake must quarantine the adapter
transparently with a clear reason rather than crash the catalog — exactly
the behavior docs/03 requires for any model that fails intake.

Each test is guarded by `skipif`: it asserts quarantine only in an
environment where the backing library is genuinely absent (e.g. CI, which
installs `.[ui,search,dev]` but not `.[models]`). In an environment that
*does* have the library installed the constructor is expected to succeed,
so the quarantine assertion no longer applies and the test skips — the
admitted-and-runs path is covered by tests/integration/test_catalog_scale.
"""

from __future__ import annotations

from importlib.util import find_spec

import pytest

from lqe.models.adapters.arch_vol_adapter import ArchVolAdapter
from lqe.models.adapters.johansen_adapter import JohansenBasketAdapter
from lqe.models.adapters.pypfopt_adapter import PyPortfolioOptAdapter
from lqe.models.adapters.riskfolio_adapter import RiskfolioAdapter
from lqe.models.adapters.skfolio_adapter import SkfolioOptimizerAdapter
from lqe.models.adapters.statsmodels_pairs_adapter import StatsmodelsPairsAdapter
from lqe.models.catalog import intake_check
from lqe.models.manifest import DataNeeds, Family, ModelManifest, Sleeve

SYMBOL = "BTC-USDT"
UNIVERSE = {"BTC-USDT": [100.0, 101.0, 102.0, 103.0], "ETH-USDT": [10.0, 10.5, 10.2, 10.8]}


def _absent(*import_names: str) -> pytest.MarkDecorator:
    """Skip a quarantine test unless every backing import is genuinely
    missing — the assertion only makes sense when the library is absent."""
    present = [name for name in import_names if find_spec(name) is not None]
    return pytest.mark.skipif(
        bool(present),
        reason=f"backing lib installed ({', '.join(present)}); adapter admits, quarantine N/A",
    )


def _manifest(
    model_id: str, family: Family, lib: str, sleeve: Sleeve = "stat_arb"
) -> ModelManifest:
    return ModelManifest(
        id=model_id, family=family, sleeve=sleeve, one_liner="heavy-lib adapter smoke test",
        economic_rationale="n/a - intake/quarantine smoke test only",
        data_needs=DataNeeds(instruments=2, kind="OHLCV"), oss_libs=[lib],
        params_schema={}, failure_modes=["requires the optional 'models' extra"],
    )


@_absent("statsmodels")
def test_statsmodels_pairs_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("pairs_demo", "pairs", "statsmodels"),
        lambda: StatsmodelsPairsAdapter(
            symbol=SYMBOL, name="pairs_demo", hedge_closes=[10.0, 10.5, 10.2, 10.8]
        ),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)


@_absent("statsmodels")
def test_johansen_basket_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("stat_arb_johansen_demo", "pairs", "statsmodels"),
        lambda: JohansenBasketAdapter(
            symbol=SYMBOL, name="stat_arb_johansen_demo", basket=("ETH-USDT",)
        ),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)


@_absent("arch")
def test_arch_vol_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("vol_garch_demo", "volatility", "arch"),
        lambda: ArchVolAdapter(symbol=SYMBOL, name="vol_garch_demo"),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)


@_absent("pypfopt")
def test_pypfopt_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("portfolio_pypfopt_demo", "portfolio", "PyPortfolioOpt"),
        lambda: PyPortfolioOptAdapter(
            symbol=SYMBOL, name="portfolio_pypfopt_demo", universe_closes=UNIVERSE
        ),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)


@_absent("skfolio")
def test_skfolio_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("portfolio_skfolio_demo", "portfolio", "skfolio"),
        lambda: SkfolioOptimizerAdapter(
            symbol=SYMBOL, name="portfolio_skfolio_demo", universe_closes=UNIVERSE
        ),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)


@_absent("riskfolio")
def test_riskfolio_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("riskalloc_riskfolio_demo", "risk_allocation", "riskfolio-lib"),
        lambda: RiskfolioAdapter(
            symbol=SYMBOL, name="riskalloc_riskfolio_demo", universe_closes=UNIVERSE
        ),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)
