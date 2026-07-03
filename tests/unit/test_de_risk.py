"""docs/02 §2.4, docs/06 §6.4: the de-risk action (cut exposure / pause /
retire) — the graduated response, distinct from a full kill. Deciding
*when* to de-risk is M8/M9's job; this tests the mechanism itself.
"""

from __future__ import annotations

from decimal import Decimal

from lqe.risk.de_risk import DeRiskController


def test_fresh_model_may_open_entries_at_full_size() -> None:
    de_risk = DeRiskController()
    assert de_risk.may_open_new_entries("trend_ma_cross") is True
    assert de_risk.exposure_multiplier("trend_ma_cross") == Decimal("1")


def test_reduce_scales_down_but_still_allows_entries() -> None:
    de_risk = DeRiskController()
    event = de_risk.apply(
        model_id="trend_ma_cross", action="REDUCE", reason="drawdown warning",
        reduce_to=Decimal("0.3"),
    )
    assert event.action == "REDUCE"
    assert event.models == ["trend_ma_cross"]
    assert de_risk.may_open_new_entries("trend_ma_cross") is True
    assert de_risk.exposure_multiplier("trend_ma_cross") == Decimal("0.3")


def test_reduce_never_increases_an_existing_tighter_multiplier() -> None:
    de_risk = DeRiskController()
    de_risk.apply(model_id="m", action="REDUCE", reason="first cut", reduce_to=Decimal("0.3"))
    de_risk.apply(model_id="m", action="REDUCE", reason="looser cut", reduce_to=Decimal("0.8"))
    assert de_risk.exposure_multiplier("m") == Decimal("0.3")  # the tighter cut sticks


def test_pause_blocks_new_entries_but_keeps_full_exposure_multiplier() -> None:
    de_risk = DeRiskController()
    de_risk.apply(model_id="m", action="PAUSE", reason="degradation review")
    assert de_risk.may_open_new_entries("m") is False
    assert de_risk.exposure_multiplier("m") == Decimal("1")


def test_retire_blocks_entries_and_zeroes_exposure() -> None:
    de_risk = DeRiskController()
    de_risk.apply(model_id="m", action="RETIRE", reason="repeated re-validation failure")
    assert de_risk.may_open_new_entries("m") is False
    assert de_risk.exposure_multiplier("m") == Decimal("0")


def test_de_risk_state_is_per_model() -> None:
    de_risk = DeRiskController()
    de_risk.apply(model_id="m1", action="RETIRE", reason="test")
    assert de_risk.may_open_new_entries("m1") is False
    assert de_risk.may_open_new_entries("m2") is True  # unaffected
