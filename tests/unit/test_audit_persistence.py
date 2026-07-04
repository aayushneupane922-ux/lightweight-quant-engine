"""Perf phase 2c: append-only audit persistence.

`write_jsonl` truncates and re-serializes the WHOLE log -- fine for a
one-shot export, but the live loop called it every poll, so per-poll I/O
grew with session length. `append_jsonl` writes only `records[start:]`
with identical serialization; a session that appends per poll produces a
byte-identical file to one final full rewrite, and `from_jsonl`'s
fail-loud verification is unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lqe.core.clock import ManualClock
from lqe.core.engine import AuditLog, Engine
from lqe.core.events import ControlEvent

START = datetime(2026, 1, 1, tzinfo=UTC)


def _engine_with(n: int) -> Engine:
    clock = ManualClock(START)
    engine = Engine(run_id="persist-test", book="sandbox", clock=clock)
    for i in range(n):
        clock.set(START + timedelta(minutes=i))
        engine.emit(
            "ControlEvent",
            ControlEvent(command="START", source="test", operator="t", note=f"n{i}"),
        )
    return engine


def test_appending_in_batches_is_byte_identical_to_one_full_write(tmp_path: Path) -> None:
    engine = _engine_with(9)
    full = tmp_path / "full.jsonl"
    engine.audit.write_jsonl(full)

    appended = tmp_path / "appended.jsonl"
    cursor = engine.audit.append_jsonl(appended, start=0)  # first batch: everything so far
    assert cursor == 9

    clock = engine.clock
    for i in range(9, 15):
        clock.set(START + timedelta(minutes=i))  # type: ignore[attr-defined]
        engine.emit(
            "ControlEvent",
            ControlEvent(command="START", source="test", operator="t", note=f"n{i}"),
        )
        cursor = engine.audit.append_jsonl(appended, start=cursor)
    assert cursor == 15

    engine.audit.write_jsonl(full)
    assert appended.read_bytes() == full.read_bytes()


def test_appended_file_loads_and_verifies(tmp_path: Path) -> None:
    engine = _engine_with(5)
    out = tmp_path / "audit.jsonl"
    cursor = engine.audit.append_jsonl(out, start=0)
    engine.emit(
        "ControlEvent", ControlEvent(command="STOP", source="test", operator="t", note="end")
    )
    engine.audit.append_jsonl(out, start=cursor)

    loaded = AuditLog.from_jsonl(out)
    assert loaded.verify()
    assert len(loaded.records) == 6
    assert loaded.records[-1].payload["note"] == "end"


def test_append_with_start_beyond_end_writes_nothing(tmp_path: Path) -> None:
    engine = _engine_with(3)
    out = tmp_path / "audit.jsonl"
    engine.audit.append_jsonl(out, start=0)
    before = out.read_bytes()
    cursor = engine.audit.append_jsonl(out, start=3)
    assert cursor == 3
    assert out.read_bytes() == before


def test_tampered_appended_file_still_fails_loud(tmp_path: Path) -> None:
    engine = _engine_with(4)
    out = tmp_path / "audit.jsonl"
    engine.audit.append_jsonl(out, start=0)
    lines = out.read_text(encoding="utf-8").splitlines()
    out.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")  # drop the tail record

    engine.emit(
        "ControlEvent", ControlEvent(command="STOP", source="test", operator="t", note="post")
    )
    engine.audit.append_jsonl(out, start=4)  # append after external truncation -> chain gap
    with pytest.raises(ValueError, match="hash-chain"):
        AuditLog.from_jsonl(out)
