"""The read-only view a `Strategy` gets of engine state (docs/11 §11.2).

A `Strategy` never reaches into the engine, accounting, or broker directly
— it only ever sees a `Context` snapshot, rebuilt fresh each bar by the
session loop. This is what keeps a strategy's decision deterministic and
side-effect-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from lqe.core.types import Symbol


@dataclass(frozen=True)
class Context:
    symbol: Symbol
    position_qty: Decimal
