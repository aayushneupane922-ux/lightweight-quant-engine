"""Merge two independently hash-chained audit logs into one chronologically
ordered, display-only event list (post-v1.0 extension, user-requested).

The live fleet runner (trading) and the `Orchestrator` (autonomy) each keep
their own `Engine`/`AuditLog` on purpose — `Orchestrator` already
constructs and owns its engine internally (docs/10 M8), and changing that
shared-vs-owned contract would touch a well-tested, self-contained class for
a display concern only. Instead, this module produces a read-only,
chronologically merged **view** for `StateReader`: each source's hash chain
remains independently verifiable via its own `AuditLog.verify()`; the merged
list is for rendering the two activity streams side by side in one desk,
nothing here is ever written back or re-verified as a single chain.
"""

from __future__ import annotations

from lqe.core.engine import Engine
from lqe.core.events import EventEnvelope


def merged_records(*engines: Engine) -> list[EventEnvelope]:
    """Chronologically interleave every engine's records (by sim_ts, then
    wall_ts as a stable tiebreaker for same-instant events, then each
    source's own seq), renumbering `seq` 1..N for the merged view only --
    the original envelopes (and their hashes) are untouched."""
    records = [r for engine in engines for r in engine.audit.records]
    records.sort(key=lambda r: (r.sim_ts, r.wall_ts, r.run_id, r.seq))
    return [r.model_copy(update={"seq": i + 1}) for i, r in enumerate(records)]


def _key(r: EventEnvelope) -> tuple[object, ...]:
    return (r.sim_ts, r.wall_ts, r.run_id, r.seq)


class IncrementalMerge:
    """A persistent merged view that only merges each poll's NEW records
    (perf phase 2a) instead of re-sorting + copying the whole ever-growing
    log every cycle.

    Both source chains grow monotonically in `(sim_ts, wall_ts, run_id,
    seq)` during a live session (the trade clock only moves forward and the
    orchestrator's clock is set to the latest bar), so new records sort
    after everything already merged and the prefix's renumbered seqs never
    change -- which the desk's `after_seq`/`lastBlotterSeq` polling depends
    on. If a new record ever sorts BEFORE the last merged key (a wall-clock
    anomaly), we fall back to a full `merged_records()` rebuild rather than
    mis-order the view."""

    def __init__(self) -> None:
        self.merged: list[EventEnvelope] = []
        # True when the last extend() had to rebuild the whole view (so the
        # already-merged prefix's renumbered seqs may have shifted) -- a
        # consumer holding derived state over the prefix must rebuild too.
        self.last_extend_rebuilt = False
        self._consumed: dict[int, int] = {}  # id(engine) -> records consumed

    def extend(self, *engines: Engine) -> list[EventEnvelope]:
        """Merge every engine's new tail into the persistent view; returns
        just the newly appended (renumbered) records."""
        self.last_extend_rebuilt = False
        tails: list[list[EventEnvelope]] = []
        for engine in engines:
            consumed = self._consumed.get(id(engine), 0)
            tails.append(engine.audit.records_since(consumed))
            self._consumed[id(engine)] = engine.audit.record_count()

        new = sorted((r for tail in tails for r in tail), key=_key)
        if not new:
            return []

        if self.merged and _key(new[0]) < _key(self.merged[-1]):
            # out-of-order tail: rebuild the whole view; renumbered seqs may
            # shift, which full-refresh consumers (a swapped-in StateReader)
            # absorb on their next frame.
            self.merged = merged_records(*engines)
            self.last_extend_rebuilt = True
            return self.merged

        base = len(self.merged)
        appended = [r.model_copy(update={"seq": base + i + 1}) for i, r in enumerate(new)]
        self.merged.extend(appended)
        return appended
