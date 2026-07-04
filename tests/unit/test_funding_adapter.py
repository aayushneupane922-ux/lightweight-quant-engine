"""`CcxtFundingRateAdapter` (docs/14 v4 sleeve F): must call only the public
`fetch_funding_rate_history` endpoint, translate raw ccxt rows into real
`FundingRateEvent`s, honor `start`/`end` bounds, and use the symbol
registry's native-symbol mapping when one is supplied -- mirrors
`ccxt_adapter.py`'s own test-double pattern (a fake exchange object
injected via the constructor, no real network calls).
"""

from __future__ import annotations

from datetime import UTC, datetime

from lqe.core.events import FundingRateEvent
from lqe.core.types import SymbolRecord
from lqe.data.funding_adapter import CcxtFundingRateAdapter
from lqe.data.symbols import SymbolRegistry


class _FakeExchange:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, int | None]] = []

    def fetch_funding_rate_history(
        self, native_symbol: str, since: int | None = None
    ) -> list[dict[str, object]]:
        self.calls.append((native_symbol, since))
        return self._rows


def _row(ts: datetime, rate: float) -> dict[str, object]:
    return {"timestamp": int(ts.timestamp() * 1000), "fundingRate": rate}


def test_stream_yields_real_funding_rate_events() -> None:
    rows = [
        _row(datetime(2026, 1, 1, tzinfo=UTC), 0.0001),
        _row(datetime(2026, 1, 1, 8, tzinfo=UTC), -0.0002),
    ]
    exchange = _FakeExchange(rows)
    adapter = CcxtFundingRateAdapter("binance", exchange=exchange)

    events = list(adapter.stream("BTC-USDT-PERP"))

    assert events == [
        FundingRateEvent(
            exchange="binance", symbol="BTC-USDT-PERP", ts=datetime(2026, 1, 1, tzinfo=UTC),
            rate=0.0001, source_version="ccxt:binance",
        ),
        FundingRateEvent(
            exchange="binance", symbol="BTC-USDT-PERP", ts=datetime(2026, 1, 1, 8, tzinfo=UTC),
            rate=-0.0002, source_version="ccxt:binance",
        ),
    ]


def test_stream_honors_the_end_bound() -> None:
    rows = [
        _row(datetime(2026, 1, 1, tzinfo=UTC), 0.0001),
        _row(datetime(2026, 1, 2, tzinfo=UTC), 0.0002),
    ]
    exchange = _FakeExchange(rows)
    adapter = CcxtFundingRateAdapter("binance", exchange=exchange)

    events = list(adapter.stream("BTC-USDT-PERP", end=datetime(2026, 1, 1, 12, tzinfo=UTC)))

    assert len(events) == 1
    assert events[0].ts == datetime(2026, 1, 1, tzinfo=UTC)


def test_stream_passes_the_start_bound_as_since_ms() -> None:
    exchange = _FakeExchange([])
    adapter = CcxtFundingRateAdapter("binance", exchange=exchange)

    list(adapter.stream("BTC-USDT-PERP", start=datetime(2026, 1, 1, tzinfo=UTC)))

    native, since = exchange.calls[0]
    assert native == "BTC/USDT/PERP"  # no registry supplied -> default '-'->'/' conversion
    assert since == int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)


def test_stream_uses_the_registry_native_symbol_when_supplied() -> None:
    registry = SymbolRegistry()
    registry.register(
        SymbolRecord(
            canonical="BTC-USDT-PERP", exchange="binance", native_symbol="BTC/USDT:USDT",
            base="BTC", quote="USDT", active=True, listed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    exchange = _FakeExchange([])
    adapter = CcxtFundingRateAdapter("binance", exchange=exchange, registry=registry)

    list(adapter.stream("BTC-USDT-PERP"))

    native, _ = exchange.calls[0]
    assert native == "BTC/USDT:USDT"


def test_adapter_has_no_trading_methods() -> None:
    forbidden = {
        "create_order", "createOrder", "cancel_order", "cancelOrder",
        "create_market_order", "create_limit_order", "withdraw",
    }
    for name in forbidden:
        assert not hasattr(CcxtFundingRateAdapter, name)
