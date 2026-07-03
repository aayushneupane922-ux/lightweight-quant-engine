"""Typed exceptions (docs/11 §11.0). Fail closed.

Grows milestone-by-milestone: only the errors an already-built module can
actually raise live here. `RiskRejected`/`ReconciliationError`/`GateError`
join once risk/ and autonomy/promotion_gate.py exist.
"""

from __future__ import annotations


class LqeError(Exception):
    """Base class for all lqe-specific errors."""


class ConfigError(LqeError):
    """A config failed validation or would enable a disallowed mode."""


class LockoutViolation(LqeError):
    """Code attempted to bypass a structural paper-only safety lockout."""


class DataQualityError(LqeError):
    """A data-validation check failed; the data is quarantined, not trusted."""
