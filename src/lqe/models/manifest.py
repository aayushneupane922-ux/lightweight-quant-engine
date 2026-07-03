"""The model manifest (docs/03 §3.3) — the single source the catalog
renders. `status` may only ever be author-declared as `unproven` at
intake; only a passing `PromotionGate` run (M4) may later mark a model
`validated`, and the catalog's own `is_validated()` check goes through the
experiment registry, never trusts a manifest's self-reported status.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Family = Literal[
    "trend", "momentum", "mean_reversion", "pairs", "volatility",
    "regime", "portfolio", "risk_allocation", "supervised", "online",
]

_FROZEN = ConfigDict(frozen=True)


class DataNeeds(BaseModel):
    model_config = _FROZEN
    instruments: int = 1
    kind: Literal["OHLCV"] = "OHLCV"
    min_history: str = ""


class ValidationNeeds(BaseModel):
    model_config = _FROZEN
    min_trades: int = 200
    needs: list[str] = ["walk_forward", "dsr", "cost_sweep"]


class ModelManifest(BaseModel):
    model_config = _FROZEN

    id: str
    family: Family
    one_liner: str
    economic_rationale: str
    data_needs: DataNeeds
    oss_libs: list[str]
    params_schema: dict[str, str]
    failure_modes: list[str]
    validation: ValidationNeeds = ValidationNeeds()
    status: Literal["unproven", "in_research", "validated"] = "unproven"
    deterministic: bool = True
