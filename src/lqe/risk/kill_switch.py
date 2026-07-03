"""The persistent, human-owned kill switch (docs/archive/10 §10.12,
docs/archive/14 §14.5). Disk-backed so it survives a process restart.
`clear()` is the only way to reset it and requires a named operator —
there is no code path anywhere in this project (now or once autonomy
lands in M8) that supplies one; a human always has to.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class KillSwitch:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._active = False
        self._reason = ""
        if self._path is not None and self._path.exists():
            self._load()

    @classmethod
    def in_memory(cls) -> KillSwitch:
        return cls(path=None)

    @property
    def active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str:
        return self._reason

    def trigger(self, *, reason: str) -> None:
        self._active = True
        self._reason = reason
        self._persist(cleared_by=None)

    def clear(self, *, operator: str) -> None:
        if not operator:
            raise ValueError("clearing a kill switch requires a named operator")
        self._active = False
        self._reason = ""
        self._persist(cleared_by=operator)

    def _persist(self, *, cleared_by: str | None) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active": self._active,
            "reason": self._reason,
            "updated_at": datetime.now(UTC).isoformat(),
            "cleared_by": cleared_by,
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load(self) -> None:
        assert self._path is not None
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        self._active = bool(payload.get("active", False))
        self._reason = str(payload.get("reason", ""))
