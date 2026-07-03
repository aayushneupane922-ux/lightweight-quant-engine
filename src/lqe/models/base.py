"""The `Strategy` protocol (docs/11 §11.2).

`on_market` must be deterministic and causal — given the same sequence of
bars it has seen so far, it always returns the same signals. It only ever
acts on a bar's completed (close) data, never a future one.
"""

from __future__ import annotations

from typing import Protocol

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent


class Strategy(Protocol):
    name: str
    params: dict[str, object]

    def on_start(self, ctx: Context) -> None: ...

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]: ...

    def on_fill(self, ev: FillEvent, ctx: Context) -> None: ...
