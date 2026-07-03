"""Degradation detection for the tracked book (docs/02 §2.4).

The reference technique named in the roadmap is River's ADWIN/DDM. This is
a native, dependency-free, *deterministic* implementation of the same idea:
an adaptive two-window comparison over a stream of per-period performance,
plus flatness and drawdown-breach checks. Native (not River) is a
deliberate choice — the whole autonomy loop must be deterministic and
replay from the audit log (a hard rail, docs/11 §11.8), and owning this
small decision surface keeps every flag auditable with no scipy/pandas in
the runtime closure. The `DriftMonitor` interface is what a River-backed
detector would slot into if we ever wanted its exact statistics.

A drift flag is only ever a *trigger*: it makes the tracked book de-risk
and kicks off a fresh search+validation cycle (docs/02 §2.4). It never
changes the live config to chase the curve — that is the overfitting
failure this design exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DriftReason(StrEnum):
    DEGRADED = "degraded"  # recent window materially worse than the older window
    FLAT = "flat"  # no improvement over the whole window (stagnant)
    DRAWDOWN = "drawdown"  # peak-to-trough on the equity path breached the limit


@dataclass(frozen=True)
class DriftVerdict:
    drifting: bool
    reasons: tuple[DriftReason, ...]
    recent_mean: float
    baseline_mean: float
    max_drawdown: float


@dataclass(frozen=True)
class DriftMonitor:
    """Deterministic drift detector over a per-period performance stream
    (e.g. per-bar or per-day tracked-book returns).

    - `window`: how many recent periods form the "recent" half; the same
      number immediately before it is the "baseline" half.
    - `degrade_ratio`: recent mean below `degrade_ratio * baseline_mean`
      (for a positive baseline) flags DEGRADED.
    - `flat_eps`: if the best cumulative point over the window improves on
      the first by less than `flat_eps`, flags FLAT.
    - `max_drawdown`: peak-to-trough fraction on the cumulative path that
      trips DRAWDOWN.
    """

    window: int = 20
    degrade_ratio: float = 0.5
    flat_eps: float = 1e-9
    max_drawdown: float = 0.15

    def evaluate(self, returns: list[float]) -> DriftVerdict:
        if len(returns) < 2 * self.window:
            # not enough history to compare two windows — never flag (fail
            # toward "no action" so we don't de-risk on noise)
            return DriftVerdict(False, (), 0.0, 0.0, 0.0)

        recent = returns[-self.window :]
        baseline = returns[-2 * self.window : -self.window]
        recent_mean = _mean(recent)
        baseline_mean = _mean(baseline)

        reasons: list[DriftReason] = []
        if baseline_mean > 0 and recent_mean < self.degrade_ratio * baseline_mean:
            reasons.append(DriftReason.DEGRADED)

        cumulative = _cumsum(returns[-2 * self.window :])
        if max(cumulative) - cumulative[0] < self.flat_eps:
            reasons.append(DriftReason.FLAT)

        dd = _max_drawdown_fraction(cumulative)
        if dd >= self.max_drawdown:
            reasons.append(DriftReason.DRAWDOWN)

        return DriftVerdict(
            drifting=bool(reasons),
            reasons=tuple(reasons),
            recent_mean=recent_mean,
            baseline_mean=baseline_mean,
            max_drawdown=dd,
        )


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _cumsum(xs: list[float]) -> list[float]:
    out: list[float] = []
    total = 0.0
    for x in xs:
        total += x
        out.append(total)
    return out


def _max_drawdown_fraction(cumulative: list[float]) -> float:
    """Largest peak-to-trough drop on a cumulative-return path, as a
    fraction of the running peak's equity (1 + peak). Deterministic."""
    peak = cumulative[0]
    worst = 0.0
    for point in cumulative:
        peak = max(peak, point)
        base = 1.0 + peak
        if base > 0:
            drop = (peak - point) / base
            worst = max(worst, drop)
    return worst
