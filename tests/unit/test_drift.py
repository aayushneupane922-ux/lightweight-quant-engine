"""The deterministic drift monitor (docs/02 §2.4): flags degradation,
flatness, and drawdown; stays silent without enough history.
"""

from __future__ import annotations

from lqe.autonomy.drift import DriftMonitor, DriftReason


def test_insufficient_history_never_flags() -> None:
    m = DriftMonitor(window=10)
    assert m.evaluate([0.01] * 5).drifting is False
    assert m.evaluate([0.01] * 19).drifting is False  # < 2*window


def test_steady_positive_stream_does_not_flag() -> None:
    m = DriftMonitor(window=10, max_drawdown=0.5)
    verdict = m.evaluate([0.01] * 40)
    assert verdict.drifting is False


def test_recent_degradation_relative_to_baseline_flags() -> None:
    m = DriftMonitor(window=10, degrade_ratio=0.5, max_drawdown=0.99)
    returns = [0.02] * 30 + [0.005] * 10  # recent window materially worse
    verdict = m.evaluate(returns)
    assert DriftReason.DEGRADED in verdict.reasons
    assert verdict.recent_mean < verdict.baseline_mean


def test_drawdown_breach_flags() -> None:
    m = DriftMonitor(window=10, degrade_ratio=0.0, max_drawdown=0.15)
    returns = [0.01] * 20 + [-0.05] * 20  # a deep recent drawdown
    verdict = m.evaluate(returns)
    assert DriftReason.DRAWDOWN in verdict.reasons
    assert verdict.drifting is True


def test_is_deterministic() -> None:
    m = DriftMonitor(window=10)
    returns = [0.02] * 30 + [0.001] * 10
    assert m.evaluate(returns) == m.evaluate(returns)
