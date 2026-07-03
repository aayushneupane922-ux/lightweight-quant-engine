"""Sandbox vs tracked books (docs/11 §11.6, docs/02 §2.2, CLAUDE.md #4).

Two surfaces that must never be conflated:

- **SANDBOX** — where the loop explores: unvalidated experiments, aggressive,
  high churn. Anything may be tried here.
- **TRACKED** — the honest, watched book: it holds *only* configs that have
  crossed the promotion gate. A config reaches it exactly one way — through
  `promote()`, which requires a passing `GateResult` and emits a
  `PromotionEvent`. There is no other setter.

De-risking (docs/02 §2.4) reduces/pauses/retires a tracked entry on
degradation without deleting the audit trail; a paused entry can still be
replaced only by another gate-passed promotion, never by editing it in place
to chase recent performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lqe.autonomy.promotion_gate import GateResult
from lqe.core.events import PromotionEvent


@dataclass(frozen=True)
class TrackedEntry:
    model_id: str
    params: dict[str, Any]
    config_version: str
    candidate_id: str
    promoted_at: datetime
    gate_dsr: float
    gate_pbo: float


@dataclass
class TrackedBook:
    """The gate-passed book. `promote()` is the only way in, and it will
    not admit a candidate whose `GateResult.verdict` isn't PASS — the gate
    is un-bypassable at this layer too, not just inside the gate."""

    _entries: dict[str, TrackedEntry] = field(default_factory=dict)
    _version_counter: int = 0

    def promote(
        self,
        *,
        model_id: str,
        params: dict[str, Any],
        candidate_id: str,
        gate_result: GateResult,
        now: datetime,
    ) -> PromotionEvent:
        if gate_result.verdict != "PASS":
            raise ValueError(
                "TrackedBook.promote requires a PASS GateResult; "
                f"got {gate_result.verdict} — the gate is un-bypassable"
            )
        self._version_counter += 1
        config_version = f"{model_id}@v{self._version_counter}"
        self._entries[model_id] = TrackedEntry(
            model_id=model_id,
            params=dict(params),
            config_version=config_version,
            candidate_id=candidate_id,
            promoted_at=now,
            gate_dsr=gate_result.dsr,
            gate_pbo=gate_result.pbo,
        )
        return PromotionEvent(
            candidate_id=candidate_id,
            from_book="sandbox",
            to_book="tracked",
            config_version=config_version,
        )

    def get(self, model_id: str) -> TrackedEntry | None:
        return self._entries.get(model_id)

    def entries(self) -> list[TrackedEntry]:
        return list(self._entries.values())

    def __contains__(self, model_id: str) -> bool:
        return model_id in self._entries

    def __len__(self) -> int:
        return len(self._entries)
