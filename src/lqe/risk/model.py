"""The single risk gate before `make_order` (docs/archive/11, docs/06 §6.4).

Fail-closed: any hard rule hit REJECTs the whole intent immediately;
`CLAMP` hits accumulate and the tightest clamp wins. Every check — APPROVE,
CLAMP, or REJECT — returns a `RiskDecision` with the rule(s) that fired, so
nothing is ever approved silently.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from lqe.core.events import OrderIntent, RiskDecision, RiskStateEvent
from lqe.risk.kill_switch import KillSwitch
from lqe.risk.rules import ALL_RULES, PortfolioState, RiskConfig, RuleHit


class RiskModel:
    def __init__(
        self, *, config: RiskConfig | None = None, kill_switch: KillSwitch | None = None
    ) -> None:
        self.config = config or RiskConfig()
        self._kill_switch = kill_switch or KillSwitch.in_memory()

    @property
    def kill_active(self) -> bool:
        return self._kill_switch.active

    def kill(self, *, reason: str) -> None:
        self._kill_switch.trigger(reason=reason)

    def clear_kill(self, *, operator: str) -> None:
        self._kill_switch.clear(operator=operator)

    def check(self, intent: OrderIntent, state: PortfolioState) -> RiskDecision:
        state = state if not self.kill_active else _with_kill_active(state)
        hits: list[RuleHit] = []
        clamp_qty = intent.qty

        for rule in ALL_RULES:
            hit = rule(intent, state, self.config)
            if hit is None:
                continue
            hits.append(hit)
            if hit.verdict == "REJECT":
                return RiskDecision(
                    intent_ref=intent.intent_id,
                    verdict="REJECT",
                    approved_qty=Decimal("0"),
                    rule_hits=[h.rule for h in hits],
                    detail={"hits": [h.detail for h in hits]},
                )
            if hit.clamp_qty is not None:
                clamp_qty = min(clamp_qty, hit.clamp_qty)

        if not hits:
            return RiskDecision(
                intent_ref=intent.intent_id, verdict="APPROVE", approved_qty=intent.qty,
                rule_hits=[], detail={},
            )
        return RiskDecision(
            intent_ref=intent.intent_id,
            verdict="CLAMP",
            approved_qty=clamp_qty,
            rule_hits=[h.rule for h in hits],
            detail={"hits": [h.detail for h in hits]},
        )

    def on_bar(self, state: PortfolioState) -> RiskStateEvent:
        drawdown = (
            float((state.peak_equity - state.equity) / state.peak_equity)
            if state.peak_equity > 0
            else 0.0
        )
        breaches: list[str] = []
        if state.peak_equity > 0 and drawdown >= float(self.config.max_dd) and not self.kill_active:
            breaches.append("max_drawdown")
            self.kill(reason=f"max_dd breached: {drawdown:.4f}")
        if state.daily_pnl <= -self.config.max_daily_loss and not self.kill_active:
            breaches.append("max_daily_loss")
            self.kill(reason=f"max_daily_loss breached: {state.daily_pnl}")

        return RiskStateEvent(
            equity=state.equity,
            cash=state.cash,
            daily_pnl=state.daily_pnl,
            gross_exposure=state.gross_exposure,
            peak_equity=state.peak_equity,
            drawdown=drawdown,
            open_orders=state.open_orders,
            breaches=breaches,
            kill_active=self.kill_active,
        )


def _with_kill_active(state: PortfolioState) -> PortfolioState:
    if state.kill_active:
        return state
    return replace(state, kill_active=True)
