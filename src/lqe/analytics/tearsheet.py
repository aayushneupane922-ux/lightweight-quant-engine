"""Markdown tearsheet (docs/10 M4). The disclaimer is not optional
boilerplate — GUARDRAILS.md forbids any profitability claim anywhere in
the product, and a tearsheet showing metrics is exactly where that claim
would otherwise creep in.
"""

from __future__ import annotations

from lqe.analytics.metrics import Metrics
from lqe.autonomy.promotion_gate import GateResult

DISCLAIMER = (
    "**Simulated research output — no profitability is claimed or implied.** "
    "All figures are paper-trading/backtest results, not evidence of future "
    "performance. Sample size and cost assumptions are shown alongside every "
    "number; a validated verdict means the candidate passed the promotion "
    "gate's out-of-sample checks, not that it will be profitable."
)


def render_tearsheet(
    *, model_id: str, metrics: Metrics, gate_result: GateResult, cost_bps_used: float
) -> str:
    lines = [
        f"# Tearsheet — {model_id}",
        "",
        DISCLAIMER,
        "",
        f"## Verdict: {gate_result.verdict}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| DSR | {gate_result.dsr:.4f} |",
        f"| PBO | {gate_result.pbo:.4f} |",
        f"| Walk-forward OOS Sharpe | {gate_result.walk_forward_oos:.4f} |",
        f"| Cost-sensitivity survived (@ {cost_bps_used:g} bps) | {gate_result.cost_survived} |",
        f"| Beats equal-weight / buy-hold | {gate_result.beats_equal_weight} |",
        f"| Beats random-entry control | {gate_result.beats_random} |",
        "",
        "## Metrics (full sample)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| n_periods | {metrics.n_periods} |",
        f"| n_trades | {metrics.n_trades} |",
        f"| CAGR | {metrics.cagr:.4%} |",
        f"| Sharpe | {metrics.sharpe:.4f} |",
        f"| Sortino | {metrics.sortino:.4f} |",
        f"| Max drawdown | {metrics.max_drawdown:.4%} |",
        f"| Max drawdown duration (bars) | {metrics.max_drawdown_duration} |",
        f"| Calmar | {metrics.calmar:.4f} |",
        f"| Turnover | {metrics.turnover:.4f} |",
        f"| Hit rate | {metrics.hit_rate:.4%} |",
        f"| Payoff ratio | {metrics.payoff_ratio:.4f} |",
        f"| Tail ratio | {metrics.tail_ratio:.4f} |",
        "",
    ]
    if gate_result.evidence.get("fail_reasons"):
        lines.append("## Why this failed the gate")
        lines.append("")
        for reason in gate_result.evidence["fail_reasons"]:
            lines.append(f"- {reason}")
        lines.append("")
    return "\n".join(lines)
