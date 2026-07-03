"""Guarded stub for any future real-money execution adapter.

This module is never imported by `src/lqe` outside `tests/safety`. The only
`ExecutionAdapter` implementation is `PaperBroker` (`execution/paper_broker.py`,
M3). This class exists purely so a future live adapter has one obviously
locked starting point, and so tests/safety has something concrete to assert
against — it is not wired into any config or factory.
"""

from __future__ import annotations


class LiveBrokerAdapter:
    is_paper = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            "Live trading is not supported by this project. "
            "LIVE_TRADING_ENABLED is fixed False; see GUARDRAILS.md."
        )
