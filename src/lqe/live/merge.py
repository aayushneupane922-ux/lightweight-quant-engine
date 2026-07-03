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
