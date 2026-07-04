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

# docs/14 §1-2 (v4): the return-driver "sleeve" a model belongs to, for
# measuring diversification -- a different, coarser cut than `Family`.
# Models in the same sleeve are expected to be highly correlated (count as
# ~1 effective bet); diversification lives *across* sleeves. `control` is
# not one of docs/14's 13 lettered sleeves -- it's this catalog's
# deliberately-weak/cautionary model (`naive_always_long`), which isn't a
# return-driver bet at all and must never count toward any sleeve's size.
Sleeve = Literal[
    "trend_momentum", "mean_reversion", "cross_sectional", "stat_arb",
    "volatility", "carry_basis", "breakout_structure", "seasonality",
    "regime_overlay", "microstructure", "cross_exchange", "ml_signal",
    "allocator", "control",
]

_FROZEN = ConfigDict(frozen=True)


class DataNeeds(BaseModel):
    model_config = _FROZEN
    instruments: int = 1
    # "OHLCV+FUNDING" (docs/14 v4 sleeve F): needs perp funding-rate history
    # alongside spot/perp OHLCV -- a genuinely different data prerequisite
    # from every other sleeve, which reads OHLCV only.
    kind: Literal["OHLCV", "OHLCV+FUNDING"] = "OHLCV"
    min_history: str = ""


class ValidationNeeds(BaseModel):
    model_config = _FROZEN
    min_trades: int = 200
    needs: list[str] = ["walk_forward", "dsr", "cost_sweep"]


class ModelManifest(BaseModel):
    model_config = _FROZEN

    id: str
    family: Family
    sleeve: Sleeve
    one_liner: str
    economic_rationale: str
    data_needs: DataNeeds
    oss_libs: list[str]
    params_schema: dict[str, str]
    failure_modes: list[str]
    validation: ValidationNeeds = ValidationNeeds()
    status: Literal["unproven", "in_research", "validated"] = "unproven"
    deterministic: bool = True
