"""`merged_records` (post-v1.0 extension): chronologically interleaves two
independently hash-chained audit logs into one display-only, renumbered
list -- each source's own chain stays independently verifiable; only the
merged copy's `seq` changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lqe.core.clock import ManualClock
from lqe.core.engine import Engine
from lqe.core.events import ControlEvent
from lqe.live.merge import merged_records

START = datetime(2026, 1, 1, tzinfo=UTC)


def _engine(run_id: str) -> Engine:
    return Engine(run_id=run_id, book="sandbox", clock=ManualClock(START))


def _emit(engine: Engine, *, at: datetime, note: str) -> None:
    clock = engine.clock
    clock.set(at)  # type: ignore[attr-defined]
    engine.emit(
        "ControlEvent",
        ControlEvent(command="START", source="test", operator="t", note=note),
    )


def test_merged_records_interleaves_by_sim_ts() -> None:
    a = _engine("engine-a")
    b = _engine("engine-b")
    _emit(a, at=START, note="a0")
    _emit(b, at=START + timedelta(seconds=30), note="b0")
    _emit(a, at=START + timedelta(minutes=1), note="a1")
    _emit(b, at=START + timedelta(minutes=2), note="b1")

    merged = merged_records(a, b)
    notes = [r.payload["note"] for r in merged]
    assert notes == ["a0", "b0", "a1", "b1"]


def test_merged_records_are_renumbered_1_to_n() -> None:
    a = _engine("engine-a")
    b = _engine("engine-b")
    _emit(a, at=START, note="a0")
    _emit(b, at=START, note="b0")
    _emit(a, at=START + timedelta(minutes=1), note="a1")

    merged = merged_records(a, b)
    assert [r.seq for r in merged] == [1, 2, 3]


def test_merged_records_leaves_the_original_chains_untouched() -> None:
    a = _engine("engine-a")
    b = _engine("engine-b")
    _emit(a, at=START, note="a0")
    _emit(b, at=START, note="b0")

    merged_records(a, b)
    assert a.audit.verify()
    assert b.audit.verify()
    assert [r.seq for r in a.audit.records] == [1]  # original untouched, not renumbered


def test_merged_records_preserves_every_source_event() -> None:
    a = _engine("engine-a")
    b = _engine("engine-b")
    for i in range(3):
        _emit(a, at=START + timedelta(minutes=i), note=f"a{i}")
    for i in range(2):
        _emit(b, at=START + timedelta(minutes=i), note=f"b{i}")

    merged = merged_records(a, b)
    assert len(merged) == 5
