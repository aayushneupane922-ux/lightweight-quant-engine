"""Two runs of the same config+seed produce identical audit hash chains.

`event_id` and `wall_ts` are real per-run entropy (a fresh uuid4 / wall-clock
read each run) and are deliberately excluded from the hashed portion of each
record — this test proves that exclusion actually holds: the hash sequences
match even though those two fields differ between runs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lqe.core.clock import ReplayClock
from lqe.core.engine import Engine
from lqe.core.events import ControlEvent

TIMESTAMPS = [
    datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
    datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
]


def _run(run_id: str) -> Engine:
    engine = Engine(run_id=run_id, book="sandbox", clock=ReplayClock(TIMESTAMPS))
    for command in ("START", "AUTOPILOT_ON", "STOP"):
        engine.tick()
        engine.emit(
            "ControlEvent",
            ControlEvent(command=command, source="test", operator="tester"),
        )
    return engine


def test_replay_equality_same_run_id_same_hash_chain() -> None:
    run_a = _run("run-replay-1")
    run_b = _run("run-replay-1")

    hashes_a = [record.hash for record in run_a.audit.records]
    hashes_b = [record.hash for record in run_b.audit.records]
    assert hashes_a == hashes_b
    assert run_a.audit.head_hash == run_b.audit.head_hash

    event_ids_a = [record.event_id for record in run_a.audit.records]
    event_ids_b = [record.event_id for record in run_b.audit.records]
    assert event_ids_a != event_ids_b  # per-run entropy, correctly excluded from hashing


def test_different_run_id_changes_the_hash_chain() -> None:
    run_a = _run("run-replay-1")
    run_c = _run("run-replay-2")

    hashes_a = [record.hash for record in run_a.audit.records]
    hashes_c = [record.hash for record in run_c.audit.records]
    assert hashes_a != hashes_c
