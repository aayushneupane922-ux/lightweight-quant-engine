"""Data-quality checks that must pass before curated/ (docs/archive/08 §8.4).

Fail loudly; quarantine, don't silently fix. Cross-source spot-checking
(§8.4 item 7) is optional and deferred — M2 ingests a single source per
run, so there's nothing to cross-check yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from statistics import mean, pstdev

from pydantic import BaseModel, ConfigDict

from lqe.core.events import MarketEvent

TIMEFRAME_DELTAS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}

_FROZEN = ConfigDict(frozen=True)


class Gap(BaseModel):
    model_config = _FROZEN
    after: str
    before: str
    missing_bars: int


class Violation(BaseModel):
    model_config = _FROZEN
    ts_open: str
    reason: str


class ValidationReport(BaseModel):
    model_config = _FROZEN

    total_bars: int
    duplicate_timestamps: list[str] = []
    out_of_order: bool = False
    ohlc_violations: list[Violation] = []
    non_positive_price: list[Violation] = []
    negative_volume: list[Violation] = []
    zero_volume_count: int = 0
    gaps: list[Gap] = []
    outliers: list[Violation] = []

    @property
    def passed(self) -> bool:
        """Hard failures only. Gaps/outliers are annotated, not blocking —
        docs/archive/08 §8.4: "flag, don't auto-delete"; gaps mean "no
        trade over the gap", not "reject the whole ingest"."""
        return not (
            self.duplicate_timestamps
            or self.out_of_order
            or self.ohlc_violations
            or self.non_positive_price
            or self.negative_volume
        )


def validate_bars(
    bars: Sequence[MarketEvent], *, timeframe: str, outlier_sigma: float = 8.0
) -> ValidationReport:
    if not bars:
        return ValidationReport(total_bars=0)

    ordered = sorted(bars, key=lambda b: b.ts_open)
    out_of_order = [b.ts_open for b in bars] != [b.ts_open for b in ordered]

    counts: dict[datetime, int] = {}
    for bar in ordered:
        counts[bar.ts_open] = counts.get(bar.ts_open, 0) + 1
    duplicate_timestamps = [ts.isoformat() for ts, count in counts.items() if count > 1]

    ohlc_violations: list[Violation] = []
    non_positive_price: list[Violation] = []
    negative_volume: list[Violation] = []
    zero_volume_count = 0
    for bar in ordered:
        if not (bar.l <= bar.o <= bar.h and bar.l <= bar.c <= bar.h and bar.h >= bar.l):
            ohlc_violations.append(
                Violation(
                    ts_open=bar.ts_open.isoformat(), reason="low <= open,close <= high violated"
                )
            )
        if bar.o <= 0 or bar.h <= 0 or bar.l <= 0 or bar.c <= 0:
            non_positive_price.append(
                Violation(ts_open=bar.ts_open.isoformat(), reason="non-positive OHLC price")
            )
        if bar.v < 0:
            negative_volume.append(
                Violation(ts_open=bar.ts_open.isoformat(), reason="negative volume")
            )
        if bar.v == 0:
            zero_volume_count += 1

    gaps: list[Gap] = []
    delta = TIMEFRAME_DELTAS.get(timeframe)
    if delta is not None:
        for prev, curr in zip(ordered, ordered[1:], strict=False):
            expected = prev.ts_open + delta
            if curr.ts_open > expected:
                # number of expected bar slots strictly between prev and curr
                missing = round((curr.ts_open - prev.ts_open) / delta) - 1
                gaps.append(
                    Gap(
                        after=prev.ts_open.isoformat(),
                        before=curr.ts_open.isoformat(),
                        missing_bars=missing,
                    )
                )

    outliers: list[Violation] = []
    closes = [float(b.c) for b in ordered]
    if len(closes) > 2:
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] != 0
        ]
        if returns:
            mu, sigma = mean(returns), pstdev(returns)
            if sigma > 0:
                for i, r in enumerate(returns, start=1):
                    if abs(r - mu) > outlier_sigma * sigma:
                        outliers.append(
                            Violation(
                                ts_open=ordered[i].ts_open.isoformat(),
                                reason=f"return {r:.4f} beyond {outlier_sigma}-sigma ({sigma:.4f})",
                            )
                        )

    return ValidationReport(
        total_bars=len(bars),
        duplicate_timestamps=duplicate_timestamps,
        out_of_order=out_of_order,
        ohlc_violations=ohlc_violations,
        non_positive_price=non_positive_price,
        negative_volume=negative_volume,
        zero_volume_count=zero_volume_count,
        gaps=gaps,
        outliers=outliers,
    )
