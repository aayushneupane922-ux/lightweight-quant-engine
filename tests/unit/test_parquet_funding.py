"""`storage/parquet_funding.py` (docs/14 v4 sleeve F): the same idempotent,
partitioned write/read guarantee as `storage/parquet.py`'s OHLCV bars, on
funding-rate history's own (smaller) schema.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from lqe.core.events import FundingRateEvent
from lqe.storage.parquet_funding import read_funding_rates, write_funding_rates

BASE_TS = datetime(2026, 1, 1, tzinfo=UTC)


def _rate(offset_hours: int, rate: float) -> FundingRateEvent:
    return FundingRateEvent(
        exchange="binance", symbol="BTC-USDT-PERP",
        ts=BASE_TS + timedelta(hours=offset_hours), rate=rate, source_version="test",
    )


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    rates = [_rate(i * 8, 0.0001 * i) for i in range(6)]
    write_funding_rates(tmp_path, rates)

    read = read_funding_rates(tmp_path, exchange="binance", symbol="BTC-USDT-PERP")
    assert read == rates


def test_write_is_idempotent(tmp_path: Path) -> None:
    rates = [_rate(i * 8, 0.0001) for i in range(3)]
    write_funding_rates(tmp_path, rates)
    write_funding_rates(tmp_path, rates)  # same rates again

    read = read_funding_rates(tmp_path, exchange="binance", symbol="BTC-USDT-PERP")
    assert len(read) == 3  # not 6


def test_overlapping_write_merges_by_timestamp(tmp_path: Path) -> None:
    first = [_rate(0, 0.0001), _rate(8, 0.0002)]
    write_funding_rates(tmp_path, first)
    second = [_rate(8, 0.0002), _rate(16, 0.0003)]  # overlaps at hour 8
    write_funding_rates(tmp_path, second)

    read = read_funding_rates(tmp_path, exchange="binance", symbol="BTC-USDT-PERP")
    assert [r.ts for r in read] == [
        BASE_TS, BASE_TS + timedelta(hours=8), BASE_TS + timedelta(hours=16),
    ]


def test_read_honors_start_and_end_bounds(tmp_path: Path) -> None:
    rates = [_rate(i * 8, 0.0001) for i in range(5)]
    write_funding_rates(tmp_path, rates)

    read = read_funding_rates(
        tmp_path, exchange="binance", symbol="BTC-USDT-PERP",
        start=BASE_TS + timedelta(hours=8), end=BASE_TS + timedelta(hours=24),
    )
    assert [r.ts for r in read] == [BASE_TS + timedelta(hours=8), BASE_TS + timedelta(hours=16)]


def test_read_missing_partition_returns_empty(tmp_path: Path) -> None:
    assert read_funding_rates(tmp_path, exchange="binance", symbol="BTC-USDT-PERP") == []


def test_write_empty_sequence_is_a_no_op(tmp_path: Path) -> None:
    assert write_funding_rates(tmp_path, []) == []
