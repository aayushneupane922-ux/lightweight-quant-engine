"""The read-only view a `Strategy` gets of engine state (docs/11 §11.2).

A `Strategy` never reaches into the engine, accounting, or broker directly
— it only ever sees a `Context` snapshot, rebuilt fresh each bar by the
session loop. This is what keeps a strategy's decision deterministic and
side-effect-free.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from lqe.core.types import Symbol


@dataclass(frozen=True)
class Context:
    symbol: Symbol
    position_qty: Decimal
    # docs/14 (v4) sleeves C/D: the most-recently-seen close for every
    # symbol the session has observed a bar for (including symbols other
    # than `symbol`), snapshotted fresh each bar -- lets a cross-sectional
    # or basket strategy rank/compare a universe without reaching into the
    # engine itself. Empty for an ordinary single-symbol session/strategy;
    # backward compatible by default, so no existing call site changes.
    universe_closes: Mapping[Symbol, Decimal] = field(default_factory=dict)
