from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lqe.core.events import FundingRateEvent, MarketEvent
from lqe.data.validate import validate_bars, validate_funding_rates

BASE_TS = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(offset_minutes: int, o: str, h: str, low: str, c: str, v: float = 1.0) -> MarketEvent:
    return MarketEvent(
        exchange="binance",
        symbol="BTC-USDT",
        timeframe="1m",
        ts_open=BASE_TS + timedelta(minutes=offset_minutes),
        o=Decimal(o),
        h=Decimal(h),
        l=Decimal(low),
        c=Decimal(c),
        v=v,
        source_version="test",
    )


def test_clean_bars_pass() -> None:
    bars = [_bar(i, "100", "101", "99", "100.5") for i in range(5)]
    report = validate_bars(bars, timeframe="1m")
    assert report.passed is True
    assert report.total_bars == 5
    assert report.gaps == []


def test_duplicate_timestamp_fires() -> None:
    bars = [_bar(0, "100", "101", "99", "100.5"), _bar(0, "100", "101", "99", "100.5")]
    report = validate_bars(bars, timeframe="1m")
    assert report.passed is False
    assert len(report.duplicate_timestamps) == 1


def test_out_of_order_fires() -> None:
    bars = [_bar(1, "100", "101", "99", "100.5"), _bar(0, "100", "101", "99", "100.5")]
    report = validate_bars(bars, timeframe="1m")
    assert report.out_of_order is True
    assert report.passed is False


def test_ohlc_sanity_fires_when_high_below_low() -> None:
    bars = [_bar(0, "100", "99", "101", "100")]  # high < low
    report = validate_bars(bars, timeframe="1m")
    assert report.passed is False
    assert len(report.ohlc_violations) == 1


def test_ohlc_sanity_fires_when_open_outside_range() -> None:
    bars = [_bar(0, "200", "101", "99", "100")]  # open > high
    report = validate_bars(bars, timeframe="1m")
    assert report.passed is False
    assert len(report.ohlc_violations) == 1


def test_non_positive_price_fires() -> None:
    bars = [_bar(0, "0", "1", "0", "0.5")]
    report = validate_bars(bars, timeframe="1m")
    assert report.passed is False
    assert len(report.non_positive_price) == 1


def test_negative_volume_fires() -> None:
    bars = [_bar(0, "100", "101", "99", "100.5", v=-1.0)]
    report = validate_bars(bars, timeframe="1m")
    assert report.passed is False
    assert len(report.negative_volume) == 1


def test_zero_volume_is_flagged_but_not_blocking() -> None:
    bars = [_bar(i, "100", "101", "99", "100.5", v=0.0) for i in range(3)]
    report = validate_bars(bars, timeframe="1m")
    assert report.zero_volume_count == 3
    assert report.passed is True


def test_gap_report_detects_missing_bars() -> None:
    bars = [_bar(0, "100", "101", "99", "100.5"), _bar(5, "100", "101", "99", "100.5")]
    report = validate_bars(bars, timeframe="1m")
    assert report.passed is True  # gaps annotate, never block
    assert len(report.gaps) == 1
    assert report.gaps[0].missing_bars == 4


def test_outlier_return_is_flagged_but_not_blocking() -> None:
    closes = ["100"] * 20 + ["1000"]  # one huge jump
    bars = [
        _bar(i, c, c, c, c) for i, c in enumerate(closes)
    ]
    report = validate_bars(bars, timeframe="1m", outlier_sigma=3.0)
    assert report.passed is True
    assert len(report.outliers) >= 1


def test_empty_input_reports_zero_bars() -> None:
    report = validate_bars([], timeframe="1m")
    assert report.total_bars == 0
    assert report.passed is True


# --- validate_funding_rates (docs/14 v4 sleeve F) ------------------------


def _rate(offset_hours: int, rate: float) -> FundingRateEvent:
    return FundingRateEvent(
        exchange="binance", symbol="BTC-USDT-PERP",
        ts=BASE_TS + timedelta(hours=offset_hours), rate=rate, source_version="test",
    )


def test_clean_funding_rates_pass() -> None:
    rates = [_rate(i * 8, 0.0001) for i in range(5)]
    report = validate_funding_rates(rates)
    assert report.passed is True
    assert report.total_rates == 5


def test_funding_duplicate_timestamp_fires() -> None:
    rates = [_rate(0, 0.0001), _rate(0, 0.0002)]
    report = validate_funding_rates(rates)
    assert report.passed is False
    assert len(report.duplicate_timestamps) == 1


def test_funding_out_of_order_fires() -> None:
    rates = [_rate(8, 0.0001), _rate(0, 0.0002)]
    report = validate_funding_rates(rates)
    assert report.out_of_order is True
    assert report.passed is False


def test_implausible_funding_rate_blocks() -> None:
    rates = [_rate(0, 0.0001), _rate(8, 0.5)]  # 50%/interval -- no real exchange allows this
    report = validate_funding_rates(rates)
    assert report.passed is False
    assert len(report.implausible_rates) == 1


def test_notable_but_plausible_funding_rate_is_flagged_not_blocking() -> None:
    rates = [_rate(0, 0.0001), _rate(8, 0.03)]  # 3%/interval -- real but rare
    report = validate_funding_rates(rates)
    assert report.passed is True
    assert len(report.notable_rates) == 1


def test_empty_funding_input_reports_zero_rates() -> None:
    report = validate_funding_rates([])
    assert report.total_rates == 0
    assert report.passed is True
