"""The deterministic, single-threaded, seq-ordered event loop (docs/06 §6.1).

`AuditLog` is the hash-chained record of everything that happened in a run;
`Engine` is what advances the clock and appends to it. `event_id` and
`wall_ts` are real, non-deterministic values (a genuine uuid4 / wall-clock
read) but are excluded from the hashed portion of each record — so two runs
with identical `run_id`, seed, and inputs produce byte-identical hash
chains even though those two metadata fields differ between runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from lqe.core import determinism
from lqe.core.bus import EventBus
from lqe.core.clock import Clock
from lqe.core.events import EventEnvelope
from lqe.core.types import Book, RunId


def _hashed_record(
    *, run_id: RunId, seq: int, book: Book, sim_ts: datetime, event_type: str,
    payload: dict[str, Any], prev_hash: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "seq": seq,
        "book": book,
        "sim_ts": sim_ts.isoformat(),
        "type": event_type,
        "payload": payload,
        "prev_hash": prev_hash,
    }


class AuditLog:
    """Append-only, hash-chained sequence of `EventEnvelope`s."""

    def __init__(self) -> None:
        self._records: list[EventEnvelope] = []
        self._prev_hash = determinism.GENESIS_HASH

    def append(
        self, *, event_type: str, run_id: RunId, seq: int, book: Book, sim_ts: datetime,
        payload: BaseModel,
    ) -> EventEnvelope:
        wall_ts = datetime.now(UTC)
        payload_json = payload.model_dump(mode="json")
        record = _hashed_record(
            run_id=run_id, seq=seq, book=book, sim_ts=sim_ts, event_type=event_type,
            payload=payload_json, prev_hash=self._prev_hash,
        )
        record_hash = determinism.compute_hash(self._prev_hash, record)
        envelope = EventEnvelope(
            event_id=str(uuid4()),
            run_id=run_id,
            seq=seq,
            book=book,
            sim_ts=sim_ts,
            wall_ts=wall_ts,
            type=event_type,
            prev_hash=self._prev_hash,
            hash=record_hash,
            payload=payload_json,
        )
        self._records.append(envelope)
        self._prev_hash = record_hash
        return envelope

    def verify(self) -> bool:
        prev_hash = determinism.GENESIS_HASH
        for envelope in self._records:
            record = _hashed_record(
                run_id=envelope.run_id, seq=envelope.seq, book=envelope.book,
                sim_ts=envelope.sim_ts, event_type=envelope.type, payload=envelope.payload,
                prev_hash=prev_hash,
            )
            expected = determinism.compute_hash(prev_hash, record)
            if expected != envelope.hash or envelope.prev_hash != prev_hash:
                return False
            prev_hash = envelope.hash
        return True

    @property
    def records(self) -> list[EventEnvelope]:
        return list(self._records)

    @property
    def head_hash(self) -> str:
        return self._prev_hash


class Engine:
    """Ties a `Clock` and `EventBus` to a hash-chained `AuditLog`."""

    def __init__(
        self, *, run_id: RunId, book: Book, clock: Clock, bus: EventBus | None = None
    ) -> None:
        self.run_id = run_id
        self.book = book
        self.clock = clock
        self.bus = bus or EventBus()
        self.audit = AuditLog()
        self._seq = 0

    def tick(self) -> datetime | None:
        return self.clock.advance()

    def emit(self, event_type: str, payload: BaseModel) -> EventEnvelope:
        self._seq += 1
        envelope = self.audit.append(
            event_type=event_type,
            run_id=self.run_id,
            seq=self._seq,
            book=self.book,
            sim_ts=self.clock.now(),
            payload=payload,
        )
        self.bus.publish(envelope)
        return envelope
