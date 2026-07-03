"""De-risk actions (docs/02 §2.4, docs/06 §6.4): the graduated response to
degradation — cut exposure, pause new entries, or retire a model entirely.
Distinct from the KILL switch (a full stop of everything): de-risking
protects capital on one model without halting the whole book, and an
existing position may still be closed out while paused/retired (same
"reduce risk is always allowed" principle as the kill switch).

Deciding *when* to de-risk — comparing live performance against history —
is the autonomy loop's job (M8/M9, docs/02 §2.4's "de-risk-then-revalidate"
response). This module is the mechanism that loop will call; for now it's
invoked directly (by a human or a test), which is exactly M5's scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from lqe.core.events import DeRiskEvent


@dataclass
class DeRiskState:
    paused: bool = False
    retired: bool = False
    exposure_multiplier: Decimal = Decimal("1")


@dataclass
class DeRiskController:
    _state: dict[str, DeRiskState] = field(default_factory=dict)

    def state_for(self, model_id: str) -> DeRiskState:
        return self._state.setdefault(model_id, DeRiskState())

    def apply(
        self,
        *,
        model_id: str,
        action: Literal["REDUCE", "PAUSE", "RETIRE"],
        reason: str,
        reduce_to: Decimal = Decimal("0.5"),
    ) -> DeRiskEvent:
        state = self.state_for(model_id)
        if action == "REDUCE":
            state.exposure_multiplier = min(state.exposure_multiplier, reduce_to)
        elif action == "PAUSE":
            state.paused = True
        elif action == "RETIRE":
            state.retired = True
            state.paused = True
            state.exposure_multiplier = Decimal("0")
        return DeRiskEvent(reason=reason, models=[model_id], action=action)

    def may_open_new_entries(self, model_id: str) -> bool:
        """Whether the model may still generate new (non-exit) intents —
        false once paused or retired. Closing an existing position is
        never blocked here; that's the sizer/strategy's own EXIT path."""
        state = self.state_for(model_id)
        return not state.paused and not state.retired

    def exposure_multiplier(self, model_id: str) -> Decimal:
        return self.state_for(model_id).exposure_multiplier
