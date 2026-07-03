"""Shared type aliases + shared domain records (docs/11 §11.0/§11.1)."""

from __future__ import annotations

import decimal
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

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


class SymbolRecord(BaseModel):
    """One canonical symbol-registry row (docs/06 §6.3). Lives in `core`
    because it is shared kernel data: `data` produces it (symbol discovery)
    and `storage` persists it (the DuckDB `symbols` table) — keeping it here
    means neither package has to import the other for the type, so the
    data↔storage layering stays one-directional (docs/11 §11.1)."""

    model_config = ConfigDict(frozen=True)

    canonical: Symbol
    exchange: str
    native_symbol: str
    base: str
    quote: str
    active: bool = True
    listed_at: datetime
    delisted_at: datetime | None = None
