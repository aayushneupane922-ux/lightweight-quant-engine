"""ccxt-backed `MarketDataAdapter` — public OHLCV endpoints only (docs/06 §6.3).

Never calls `create_order`/`cancel_order`/`create_market_order`/
`create_limit_order`/`withdraw` or any other trading method — this module
only ever calls `fetch_ohlcv`. Enforced by
`tests/safety/test_no_order_capable_data_adapter.py` (a grep/AST scan of
`src/lqe`, not just this file).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from lqe.core.events import MarketEvent
from lqe.core.types import Symbol, Timeframe
from lqe.data.base import DataCapabilities
from lqe.data.symbols import SymbolRegistry, to_ccxt_symbol


class CcxtMarketDataAdapter:
    def __init__(
        self,
        exchange_id: str,
        *,
        exchange: Any | None = None,
        registry: SymbolRegistry | None = None,
    ) -> None:
        self._exchange_id = exchange_id
        self._exchange = exchange if exchange is not None else self._build_exchange(exchange_id)
        self._registry = registry

    @staticmethod
    def _build_exchange(exchange_id: str) -> Any:
        import ccxt

        exchange_class = getattr(ccxt, exchange_id)
        return exchange_class({"enableRateLimit": True})

    def capabilities(self) -> DataCapabilities:
        return DataCapabilities(bars=True)

    def stream(
        self,
        symbols: list[Symbol],
        tf: Timeframe,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Iterator[MarketEvent]:
        # V5 M27 (Universe Core): each symbol's own bars come back from
        # `fetch_ohlcv` already time-ordered, but multiple symbols must be
        # interleaved by `ts_open` -- a `Universe` consumer downstream
        # groups bars into per-timestamp cycles and needs a genuinely
        # chronological merge across symbols, not "all of BTC, then all
        # of ETH." Bar counts per poll are small (hundreds, not millions),
        # so a plain sort-after-fetch is simpler to reason about than a
        # lazy heapq.merge and costs nothing measurable.
        all_bars = [
            bar for symbol in symbols for bar in self._stream_one(symbol, tf, start, end)
        ]
        all_bars.sort(key=lambda bar: bar.ts_open)
        yield from all_bars

    def _stream_one(
        self,
        symbol: Symbol,
        tf: Timeframe,
        start: datetime | None,
        end: datetime | None,
    ) -> Iterator[MarketEvent]:
        native = (
            self._registry.native_symbol(self._exchange_id, symbol)
            if self._registry is not None
            else to_ccxt_symbol(symbol)
        )
        since = int(start.timestamp() * 1000) if start is not None else None
        raw_bars = self._exchange.fetch_ohlcv(native, timeframe=tf, since=since)
        for ts_ms, o, h, low, c, v in raw_bars:
            ts_open = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            if end is not None and ts_open >= end:
                break
            yield MarketEvent(
                exchange=self._exchange_id,
                symbol=symbol,
                timeframe=tf,
                ts_open=ts_open,
                o=Decimal(str(o)),
                h=Decimal(str(h)),
                l=Decimal(str(low)),
                c=Decimal(str(c)),
                v=float(v),
                source_version=f"ccxt:{self._exchange_id}",
            )
