"""Core `ModelCatalog`/`intake_check` mechanics (docs/03 §3.3/§3.4): a
candidate lists only after passing every check, and any failure quarantines
transparently with the reason rather than disappearing silently.
"""

from __future__ import annotations

from lqe.models.base import Strategy
from lqe.models.catalog import ModelCatalog, intake_check
from lqe.models.manifest import DataNeeds, ModelManifest


def _manifest(**overrides: object) -> ModelManifest:
    defaults: dict[str, object] = {
        "id": "test_model",
        "family": "trend",
        "one_liner": "a test model",
        "economic_rationale": "n/a - unit test fixture",
        "data_needs": DataNeeds(instruments=1, kind="OHLCV"),
        "oss_libs": ["own"],
        "params_schema": {},
        "failure_modes": ["overfits to test fixtures"],
    }
    defaults.update(overrides)
    return ModelManifest(**defaults)  # type: ignore[arg-type]


class _FakeStrategy:
    name = "test_model"
    params: dict[str, object] = {}

    def on_start(self, ctx: object) -> None:
        return None

    def on_market(self, ev: object, ctx: object) -> list[object]:
        return []

    def on_fill(self, ev: object, ctx: object) -> None:
        return None


def _fake_factory() -> Strategy:
    return _FakeStrategy()  # type: ignore[return-value]


def test_intake_passes_a_well_formed_manifest_and_working_factory() -> None:
    result = intake_check(_manifest(), _fake_factory)
    assert result.passed
    assert result.reasons == []


def test_intake_rejects_a_non_unproven_status() -> None:
    result = intake_check(_manifest(status="validated"), _fake_factory)
    assert not result.passed
    assert any("unproven" in r for r in result.reasons)


def test_intake_rejects_a_non_deterministic_declaration() -> None:
    result = intake_check(_manifest(deterministic=False), _fake_factory)
    assert not result.passed
    assert any("deterministic" in r for r in result.reasons)


def test_intake_rejects_missing_one_liner_or_rationale() -> None:
    result = intake_check(_manifest(one_liner=""), _fake_factory)
    assert not result.passed
    assert any("one_liner" in r for r in result.reasons)


def test_intake_rejects_missing_failure_modes() -> None:
    result = intake_check(_manifest(failure_modes=[]), _fake_factory)
    assert not result.passed
    assert any("failure mode" in r for r in result.reasons)


def test_intake_rejects_a_non_permissive_library() -> None:
    result = intake_check(_manifest(oss_libs=["some-gpl-lib"]), _fake_factory)
    assert not result.passed
    assert any("allowlist" in r for r in result.reasons)


def test_intake_rejects_a_factory_that_fails_to_construct() -> None:
    def _broken_factory() -> Strategy:
        raise RuntimeError("boom")

    result = intake_check(_manifest(), _broken_factory)
    assert not result.passed
    assert any("boom" in r for r in result.reasons)


def test_catalog_register_admits_passing_models_and_quarantines_failing_ones() -> None:
    catalog = ModelCatalog()
    good = catalog.register(_manifest(), _fake_factory)
    bad = catalog.register(_manifest(id="bad_model", deterministic=False), _fake_factory)

    assert good.passed
    assert not bad.passed
    assert [e.manifest.id for e in catalog.all()] == ["test_model"]
    assert [q.model_id for q in catalog.quarantined()] == ["bad_model"]
    assert catalog.get("test_model").manifest.id == "test_model"


def test_catalog_get_raises_a_helpful_error_for_a_missing_model() -> None:
    catalog = ModelCatalog()
    try:
        catalog.get("nonexistent")
        raise AssertionError("expected KeyError")
    except KeyError as exc:
        assert "quarantine" in str(exc)


def test_catalog_by_family_filters_correctly() -> None:
    catalog = ModelCatalog()
    catalog.register(_manifest(id="trend_a", family="trend"), _fake_factory)
    catalog.register(_manifest(id="momentum_a", family="momentum"), _fake_factory)

    assert [e.manifest.id for e in catalog.by_family("trend")] == ["trend_a"]
    assert [e.manifest.id for e in catalog.by_family("momentum")] == ["momentum_a"]
    assert catalog.by_family("mean_reversion") == []
