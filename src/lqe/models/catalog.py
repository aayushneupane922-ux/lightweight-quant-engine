"""Plugin discovery, intake, and the transparent quarantine list (docs/03
§3.4). A candidate lists only after passing intake: permissive license,
manifest completeness, declared determinism, and a real construction
smoke-test. Anything that fails is quarantined with its reason — visible,
never silently dropped.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from lqe.models.base import Strategy
from lqe.models.manifest import ModelManifest

# Only the libraries this catalog actually references anywhere (docs/15
# license review); "own" marks native code with no third-party license at all.
# pandas-ta was evaluated and rejected (see pyproject.toml) — indicators are
# native ("own") instead, so it is deliberately absent from this allowlist.
_PERMISSIVE_LIBS = {
    "own": "native code",
    "skfolio": "BSD-3",
    "PyPortfolioOpt": "MIT",
    "riskfolio-lib": "BSD-3",
    "statsmodels": "BSD-3",
    "arch": "NCSA",
    "hmmlearn": "BSD-3",
    "ruptures": "BSD-2",
    "scikit-learn": "BSD-3",
    "lightgbm": "MIT",
}


@dataclass(frozen=True)
class IntakeResult:
    model_id: str
    passed: bool
    reasons: list[str]


@dataclass(frozen=True)
class QuarantineRecord:
    model_id: str
    reasons: list[str]


def intake_check(
    manifest: ModelManifest, strategy_factory: Callable[[], Strategy]
) -> IntakeResult:
    reasons: list[str] = []

    if manifest.status != "unproven":
        reasons.append("manifest must declare status=unproven at intake; only the gate promotes")
    if not manifest.deterministic:
        reasons.append("model must be declared deterministic")
    if not manifest.one_liner or not manifest.economic_rationale:
        reasons.append("manifest is missing one_liner/economic_rationale")
    if not manifest.failure_modes:
        reasons.append("manifest must list at least one known failure mode")
    for lib in manifest.oss_libs:
        if lib not in _PERMISSIVE_LIBS:
            reasons.append(f"{lib!r} is not on the permissive-license allowlist")

    try:
        strategy_factory()
    except Exception as exc:  # noqa: BLE001 - intentionally broad: any construction failure quarantines
        reasons.append(f"strategy_factory failed to construct: {exc}")

    return IntakeResult(model_id=manifest.id, passed=not reasons, reasons=reasons)


@dataclass(frozen=True)
class CatalogEntry:
    manifest: ModelManifest
    strategy_factory: Callable[[], Strategy]


@dataclass
class ModelCatalog:
    _entries: dict[str, CatalogEntry] = field(default_factory=dict)
    _quarantine: list[QuarantineRecord] = field(default_factory=list)

    def register(
        self, manifest: ModelManifest, strategy_factory: Callable[[], Strategy]
    ) -> IntakeResult:
        result = intake_check(manifest, strategy_factory)
        if result.passed:
            self._entries[manifest.id] = CatalogEntry(
                manifest=manifest, strategy_factory=strategy_factory
            )
        else:
            self._quarantine.append(QuarantineRecord(model_id=manifest.id, reasons=result.reasons))
        return result

    def get(self, model_id: str) -> CatalogEntry:
        try:
            return self._entries[model_id]
        except KeyError:
            raise KeyError(f"{model_id!r} is not in the catalog (check quarantine())") from None

    def all(self) -> list[CatalogEntry]:
        return list(self._entries.values())

    def by_family(self, family: str) -> list[CatalogEntry]:
        return [e for e in self._entries.values() if e.manifest.family == family]

    def quarantined(self) -> list[QuarantineRecord]:
        return list(self._quarantine)
