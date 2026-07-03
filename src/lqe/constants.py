"""The compile-time paper-only lockout.

The MVP is paper-only. There is no supported way to enable live trading.

Enforced elsewhere:
 - config schema (core/config.py) excludes `mode: live` and any real
   execution adapter (pydantic Enums).
 - engine startup asserts execution_adapter.is_paper is True.
 - the only ExecutionAdapter implementation is PaperBroker.
 - tests/safety forbids broker SDK imports and ccxt order-creation calls.
"""

from __future__ import annotations

LIVE_TRADING_ENABLED: bool = False
