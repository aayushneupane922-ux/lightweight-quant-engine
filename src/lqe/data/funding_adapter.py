"""ccxt-backed funding-rate data adapter (docs/14 v4 sleeve F). Public
`fetch_funding_rate_history` endpoint only (docs/06 §6.3's read-only rule
for data adapters, same as `ccxt_adapter.py`).

Never calls `create_order`/`cancel_order`/`create_market_order`/
`create_limit_order`/`withdraw` or any other trading method — enforced by
`tests/safety/test_no_order_capable_data_adapter.py` (a grep/AST scan of
the whole `src/lqe` tree, not just this file).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from lqe.core.events import FundingRateEvent
from lqe.core.types import Symbol
from lqe.data.symbols import SymbolRegistry, to_ccxt_symbol


class CcxtFundingRateAdapter:
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

    def stream(
        self,
        symbol: Symbol,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Iterator[FundingRateEvent]:
        native = (
            self._registry.native_symbol(self._exchange_id, symbol)
            if self._registry is not None
            else to_ccxt_symbol(symbol)
        )
        since = int(start.timestamp() * 1000) if start is not None else None
        raw_rates = self._exchange.fetch_funding_rate_history(native, since=since)
        for entry in raw_rates:
            ts = datetime.fromtimestamp(entry["timestamp"] / 1000, tz=UTC)
            if end is not None and ts >= end:
                break
            yield FundingRateEvent(
                exchange=self._exchange_id,
                symbol=symbol,
                ts=ts,
                rate=float(entry["fundingRate"]),
                source_version=f"ccxt:{self._exchange_id}",
            )
