"""Canonical JSON + sha256 hash-chain helpers (docs/11 §11.8).

`hash = sha256(prev_hash + canonical_json(record_without_hash))`. Canonical
JSON is sorted-key, separator-tight JSON so the same logical record always
serializes to the same bytes regardless of dict insertion order.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS_HASH = "0" * 64


def canonical_json(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_hash(prev_hash: str, record: dict[str, Any]) -> str:
    payload = canonical_json(record).encode("utf-8")
    return hashlib.sha256(prev_hash.encode("utf-8") + payload).hexdigest()
