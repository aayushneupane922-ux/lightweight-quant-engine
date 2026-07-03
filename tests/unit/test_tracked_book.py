"""`TrackedBook` (docs/11 §11.6, CLAUDE.md #4): promotion is the only way
in, and it is un-bypassable — a non-PASS `GateResult` is refused.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lqe.autonomy.books import TrackedBook
from lqe.autonomy.promotion_gate import GateResult

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _gate(verdict: str) -> GateResult:
    return GateResult(
        verdict=verdict,  # type: ignore[arg-type]
        dsr=0.99, pbo=0.1, cost_survived=True, beats_equal_weight=True,
        beats_random=True, walk_forward_oos=0.5, evidence={},
    )


def test_promote_admits_a_passing_candidate() -> None:
    book = TrackedBook()
    event = book.promote(
        model_id="trend_ma_cross", params={"fast": 5, "slow": 20},
        candidate_id="c1", gate_result=_gate("PASS"), now=NOW,
    )
    assert event.from_book == "sandbox" and event.to_book == "tracked"
    assert "trend_ma_cross" in book
    assert book.get("trend_ma_cross").params == {"fast": 5, "slow": 20}  # type: ignore[union-attr]


def test_promote_refuses_a_failing_candidate() -> None:
    book = TrackedBook()
    with pytest.raises(ValueError, match="un-bypassable"):
        book.promote(
            model_id="trend_ma_cross", params={"fast": 5, "slow": 20},
            candidate_id="c1", gate_result=_gate("FAIL"), now=NOW,
        )
    assert len(book) == 0


def test_promotion_bumps_the_config_version() -> None:
    book = TrackedBook()
    e1 = book.promote(
        model_id="m", params={"a": 1}, candidate_id="c1", gate_result=_gate("PASS"), now=NOW
    )
    e2 = book.promote(
        model_id="m", params={"a": 2}, candidate_id="c2", gate_result=_gate("PASS"), now=NOW
    )
    assert e1.config_version != e2.config_version
    assert book.get("m").params == {"a": 2}  # type: ignore[union-attr]
