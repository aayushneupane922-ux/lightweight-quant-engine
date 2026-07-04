"""`CcxtMarketDataAdapter.stream()` (V5 M27 Universe Core): given multiple
symbols, bars must come out interleaved by `ts_open`, not "all of symbol A
then all of symbol B" -- a `Universe` consumer downstream groups bars into
per-timestamp cycles and needs genuine chronological ordering across
symbols.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lqe.data.ccxt_adapter import CcxtMarketDataAdapter

_OhlcvBar = tuple[int, float, float, float, float, float]


class _FakeExchange:
    """Mimics the slice of ccxt's exchange interface this adapter calls --
    `fetch_ohlcv(symbol, timeframe, since)` returning raw OHLCV rows."""

    def __init__(self, bars_by_symbol: dict[str, list[_OhlcvBar]]) -> None:
        self._bars_by_symbol = bars_by_symbol

    def fetch_ohlcv(self, native_symbol: str, timeframe: str, since: int | None = None):
        return self._bars_by_symbol.get(native_symbol, [])


def _ts_ms(minute: int) -> int:
    return int(datetime(2026, 1, 1, 0, minute, tzinfo=UTC).timestamp() * 1000)


def test_stream_interleaves_multiple_symbols_by_ts_open() -> None:
    # BTC has bars at :00, :02, :04; ETH has bars at :01, :03, :05 -- the
    # merged stream must alternate BTC/ETH/BTC/ETH/BTC/ETH, not emit all
    # of BTC before any of ETH.
    fake = _FakeExchange(
        {
            "BTC/USDT": [
                (_ts_ms(0), 100, 101, 99, 100, 1.0),
                (_ts_ms(2), 102, 103, 101, 102, 1.0),
                (_ts_ms(4), 104, 105, 103, 104, 1.0),
            ],
            "ETH/USDT": [
                (_ts_ms(1), 10, 11, 9, 10, 2.0),
                (_ts_ms(3), 12, 13, 11, 12, 2.0),
                (_ts_ms(5), 14, 15, 13, 14, 2.0),
            ],
        }
    )
    adapter = CcxtMarketDataAdapter("binance", exchange=fake)
    bars = list(adapter.stream(["BTC-USDT", "ETH-USDT"], "1m"))

    assert [b.symbol for b in bars] == [
        "BTC-USDT", "ETH-USDT", "BTC-USDT", "ETH-USDT", "BTC-USDT", "ETH-USDT",
    ]
    assert [b.ts_open for b in bars] == sorted(b.ts_open for b in bars)


def test_stream_single_symbol_is_unaffected() -> None:
    fake = _FakeExchange(
        {"BTC/USDT": [(_ts_ms(0), 100, 101, 99, 100, 1.0), (_ts_ms(1), 101, 102, 100, 101, 1.0)]}
    )
    adapter = CcxtMarketDataAdapter("binance", exchange=fake)
    bars = list(adapter.stream(["BTC-USDT"], "1m"))
    assert [b.symbol for b in bars] == ["BTC-USDT", "BTC-USDT"]
    assert bars[0].ts_open < bars[1].ts_open


def test_stream_respects_end_boundary_per_symbol() -> None:
    fake = _FakeExchange(
        {
            "BTC/USDT": [(_ts_ms(0), 100, 101, 99, 100, 1.0), (_ts_ms(10), 100, 101, 99, 100, 1.0)],
            "ETH/USDT": [(_ts_ms(1), 10, 11, 9, 10, 2.0), (_ts_ms(11), 10, 11, 9, 10, 2.0)],
        }
    )
    adapter = CcxtMarketDataAdapter("binance", exchange=fake)
    end = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    bars = list(adapter.stream(["BTC-USDT", "ETH-USDT"], "1m", end=end))
    assert [b.symbol for b in bars] == ["BTC-USDT", "ETH-USDT"]
