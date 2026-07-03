"""Slippage models (docs/archive/10 §10.6). Pessimistic by default: a BUY
always fills worse (higher) and a SELL always fills worse (lower).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal


class FixedBpsSlippage:
    def __init__(self, bps: float) -> None:
        self._bps = Decimal(str(bps))

    def adjust(self, *, side: Literal["BUY", "SELL"], price: Decimal) -> tuple[Decimal, float]:
        factor = self._bps / Decimal("10000")
        if side == "BUY":
            adjusted = price * (Decimal("1") + factor)
        else:
            adjusted = price * (Decimal("1") - factor)
        return adjusted, float(self._bps)
