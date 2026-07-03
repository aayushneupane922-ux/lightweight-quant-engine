"""Commission model (docs/archive/10 §10.6): bps of notional, with a floor."""

from __future__ import annotations

from decimal import Decimal


class BpsCommission:
    def __init__(self, *, bps: float, min_fee: Decimal = Decimal("0")) -> None:
        self._bps = Decimal(str(bps))
        self._min_fee = min_fee

    def compute(self, *, qty: Decimal, price: Decimal) -> Decimal:
        fee = qty * price * self._bps / Decimal("10000")
        return max(fee, self._min_fee)
