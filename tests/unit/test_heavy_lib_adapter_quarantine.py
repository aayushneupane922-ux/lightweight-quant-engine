"""docs/03 §3.4 honesty check: the five heavy-lib structural adapters
(statsmodels/arch/PyPortfolioOpt/skfolio/riskfolio-lib) are lazily
imported so the base install never needs them. In *this* dev environment
none of those optional 'models'-extra packages are installed, so intake
must quarantine each one transparently with a clear reason rather than
crash the catalog — exactly the behavior docs/03 requires for any model
that fails intake. If a future environment does have `.[models]`
installed, these same constructors are expected to succeed instead (not
asserted here, since it depends on the environment).
"""

from __future__ import annotations

from lqe.models.adapters.arch_vol_adapter import ArchVolAdapter
from lqe.models.adapters.pypfopt_adapter import PyPortfolioOptAdapter
from lqe.models.adapters.riskfolio_adapter import RiskfolioAdapter
from lqe.models.adapters.skfolio_adapter import SkfolioOptimizerAdapter
from lqe.models.adapters.statsmodels_pairs_adapter import StatsmodelsPairsAdapter
from lqe.models.catalog import intake_check
from lqe.models.manifest import DataNeeds, Family, ModelManifest

SYMBOL = "BTC-USDT"
UNIVERSE = {"BTC-USDT": [100.0, 101.0, 102.0, 103.0], "ETH-USDT": [10.0, 10.5, 10.2, 10.8]}


def _manifest(model_id: str, family: Family, lib: str) -> ModelManifest:
    return ModelManifest(
        id=model_id, family=family, one_liner="heavy-lib adapter smoke test",
        economic_rationale="n/a - intake/quarantine smoke test only",
        data_needs=DataNeeds(instruments=2, kind="OHLCV"), oss_libs=[lib],
        params_schema={}, failure_modes=["requires the optional 'models' extra"],
    )


def test_statsmodels_pairs_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("pairs_demo", "pairs", "statsmodels"),
        lambda: StatsmodelsPairsAdapter(
            symbol=SYMBOL, name="pairs_demo", hedge_closes=[10.0, 10.5, 10.2, 10.8]
        ),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)


def test_arch_vol_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("vol_garch_demo", "volatility", "arch"),
        lambda: ArchVolAdapter(symbol=SYMBOL, name="vol_garch_demo"),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)


def test_pypfopt_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("portfolio_pypfopt_demo", "portfolio", "PyPortfolioOpt"),
        lambda: PyPortfolioOptAdapter(
            symbol=SYMBOL, name="portfolio_pypfopt_demo", universe_closes=UNIVERSE
        ),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)


def test_skfolio_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("portfolio_skfolio_demo", "portfolio", "skfolio"),
        lambda: SkfolioOptimizerAdapter(
            symbol=SYMBOL, name="portfolio_skfolio_demo", universe_closes=UNIVERSE
        ),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)


def test_riskfolio_adapter_quarantines_cleanly_without_the_extra() -> None:
    result = intake_check(
        _manifest("riskalloc_riskfolio_demo", "risk_allocation", "riskfolio-lib"),
        lambda: RiskfolioAdapter(
            symbol=SYMBOL, name="riskalloc_riskfolio_demo", universe_closes=UNIVERSE
        ),
    )
    assert not result.passed
    assert any("models" in r for r in result.reasons)
