"""The `MarketDataAdapter` protocol (docs/11 §11.2, docs/06 §6.3).

A `MarketDataAdapter` MUST NOT expose `create_order`/`cancel_order`/
`withdraw` or any other trading method — enforced by
`tests/safety/test_no_order_capable_data_adapter.py`. Data adapters only
ever read public market data.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe


class DataCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    bars: bool = True
    ticks: bool = False
    book: bool = False
    delayed: bool = False


class MarketDataAdapter(Protocol):
    def capabilities(self) -> DataCapabilities: ...

    def stream(
        self,
        symbols: list[Symbol],
        tf: Timeframe,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Iterator[MarketEvent]: ...
