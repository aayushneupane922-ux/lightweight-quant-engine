"""Shared type aliases (docs/11 §11.0)."""

from __future__ import annotations

import decimal
from typing import Literal

Symbol = str
"""Canonical BASE-QUOTE symbol, upper-case."""

Timeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d"]

Price = decimal.Decimal
Qty = decimal.Decimal
Bps = float

RunId = str
EventId = str
TrialId = str

Book = Literal["tracked", "sandbox"]
