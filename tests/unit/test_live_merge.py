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


# --- IncrementalMerge (perf phase 2a) ---------------------------------------
# The live loop used to re-sort + model_copy EVERY record each poll;
# IncrementalMerge keeps a persistent merged view and only merges the new
# tails. Contract: output identical to a one-shot merged_records() at every
# point, and already-merged prefix seqs never change (the desk's
# after_seq/lastBlotterSeq polling depends on that).


def test_incremental_extend_over_rounds_equals_one_shot_merge() -> None:
    from lqe.live.merge import IncrementalMerge

    a = _engine("engine-a")
    b = _engine("engine-b")
    inc = IncrementalMerge()

    _emit(a, at=START, note="a0")
    inc.extend(a, b)
    _emit(b, at=START + timedelta(seconds=30), note="b0")
    _emit(a, at=START + timedelta(minutes=1), note="a1")
    inc.extend(a, b)
    _emit(b, at=START + timedelta(minutes=2), note="b1")
    _emit(a, at=START + timedelta(minutes=3), note="a2")
    inc.extend(a, b)

    expected = merged_records(a, b)
    assert [r.seq for r in inc.merged] == [r.seq for r in expected]
    assert [r.payload["note"] for r in inc.merged] == [r.payload["note"] for r in expected]
    assert [r.hash for r in inc.merged] == [r.hash for r in expected]


def test_incremental_extend_never_renumbers_the_already_merged_prefix() -> None:
    from lqe.live.merge import IncrementalMerge

    a = _engine("engine-a")
    b = _engine("engine-b")
    inc = IncrementalMerge()
    _emit(a, at=START, note="a0")
    _emit(b, at=START + timedelta(seconds=10), note="b0")
    inc.extend(a, b)
    prefix = [(r.seq, r.hash) for r in inc.merged]

    _emit(a, at=START + timedelta(minutes=5), note="a1")
    _emit(b, at=START + timedelta(minutes=6), note="b1")
    new = inc.extend(a, b)

    assert [(r.seq, r.hash) for r in inc.merged[: len(prefix)]] == prefix
    assert [r.payload["note"] for r in new] == ["a1", "b1"]


def test_incremental_extend_falls_back_on_out_of_order_tail() -> None:
    from lqe.live.merge import IncrementalMerge

    a = _engine("engine-a")
    b = _engine("engine-b")
    inc = IncrementalMerge()
    _emit(a, at=START + timedelta(minutes=10), note="a-late")
    inc.extend(a, b)

    # a new event with an EARLIER sim_ts than the last merged key: the
    # incremental fast path can't apply; the merged view must still equal a
    # full one-shot merge (fallback), not silently mis-order.
    _emit(b, at=START, note="b-early")
    inc.extend(a, b)

    expected = merged_records(a, b)
    assert [r.payload["note"] for r in inc.merged] == [r.payload["note"] for r in expected]
    assert [r.seq for r in inc.merged] == [1, 2]


def test_incremental_extend_returns_only_the_new_tail() -> None:
    from lqe.live.merge import IncrementalMerge

    a = _engine("engine-a")
    b = _engine("engine-b")
    inc = IncrementalMerge()
    _emit(a, at=START, note="a0")
    first = inc.extend(a, b)
    second = inc.extend(a, b)  # nothing new
    assert [r.payload["note"] for r in first] == ["a0"]
    assert second == []
