"""The deliberately weak control model docs/03 §3.6 requires ("include >=1
deliberately weak model ... so the tooling visibly rejects things"). Goes
long on the first bar and never exits — no signal, no edge, pure
buy-and-hold exposure. Exists so the promotion gate and catalog honesty
tooling have something real to reject.
"""

from __future__ import annotations

from lqe.core.context import Context
from lqe.core.events import FillEvent, MarketEvent, SignalEvent
from lqe.core.types import Symbol
from lqe.models.manifest import DataNeeds, ModelManifest, ValidationNeeds

MANIFEST = ModelManifest(
    id="naive_always_long",
    family="trend",
    one_liner="Goes long on bar one and never exits. A deliberately weak control.",
    economic_rationale="None — this is buy-and-hold, kept only as an honesty control.",
    data_needs=DataNeeds(instruments=1, kind="OHLCV"),
    oss_libs=["own"],
    params_schema={},
    failure_modes=["has no edge by construction; expected to fail the promotion gate"],
    validation=ValidationNeeds(min_trades=1, needs=["walk_forward", "dsr", "cost_sweep"]),
)


class NaiveAlwaysLong:
    name = MANIFEST.id
    params: dict[str, object] = {}

    def __init__(self, *, symbol: Symbol) -> None:
        self._symbol = symbol
        self._entered = False

    def on_start(self, ctx: Context) -> None:
        self._entered = ctx.position_qty > 0

    def on_market(self, ev: MarketEvent, ctx: Context) -> list[SignalEvent]:
        if ev.symbol != self._symbol or self._entered:
            return []
        self._entered = True
        return [
            SignalEvent(
                strategy=self.name, symbol=self._symbol, direction="LONG", strength=1.0,
                intent_kind="ENTER", bar_ts=ev.ts_open, reason="naive control: always long",
            )
        ]

    def on_fill(self, ev: FillEvent, ctx: Context) -> None:
        return None


def make_strategy(symbol: Symbol) -> NaiveAlwaysLong:
    return NaiveAlwaysLong(symbol=symbol)
