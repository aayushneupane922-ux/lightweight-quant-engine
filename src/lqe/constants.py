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

# Perf phase 3c: strategy adapters keep only this many bars of raw history
# (trimmed amortized, so per-bar cost stays constant instead of growing with
# session length). Derivation of the binding constraints: the largest
# fixed-window need anywhere in the catalog/search spaces is tsmom's
# lookback 150 (+1); the real driver is `opening_range_breakout`, which
# needs every bar of the current UTC day -- 1440 1m bars + or_bars. 4096
# covers ~2.8 days of 1m bars. Window-bounded (FIR-style) indicators are
# bit-identical under the cap; recursive (EMA/Wilder) ones carry a tail
# influence <= (1-alpha)^(4096-window), < 1e-60 relative -- below float64
# resolution -- verified empirically by tests/parity/
# test_bounded_history_parity.py. If that parity test ever fails, raise
# this constant; do not weaken the test.
ADAPTER_HISTORY_CAP: int = 4096
