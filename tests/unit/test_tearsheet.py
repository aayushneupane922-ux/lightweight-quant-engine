from decimal import Decimal

from lqe.analytics.metrics import compute_metrics
from lqe.analytics.tearsheet import DISCLAIMER, render_tearsheet
from lqe.autonomy.promotion_gate import GateResult


def test_tearsheet_always_carries_the_disclaimer() -> None:
    metrics = compute_metrics(
        equity_curve=[Decimal("10000"), Decimal("10100")],
        trade_pnls=[100.0],
        trade_notionals=[Decimal("1000")],
        periods_per_year=365 * 24 * 60,
    )
    gate_result = GateResult(
        verdict="FAIL", dsr=0.1, pbo=0.8, cost_survived=False, beats_equal_weight=False,
        beats_random=False, walk_forward_oos=-0.2, evidence={"fail_reasons": ["dsr too low"]},
    )
    sheet = render_tearsheet(
        model_id="trend_ma_cross", metrics=metrics, gate_result=gate_result, cost_bps_used=10.0
    )
    assert DISCLAIMER in sheet
    assert "no profitability is claimed" in sheet.lower()
    assert "FAIL" in sheet
    assert "dsr too low" in sheet
