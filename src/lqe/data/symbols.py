"""Canonical symbol registry (docs/06 §6.3, docs/archive/08 §8.2).

Exchanges disagree on symbol spelling (`BTC/USDT` vs `XBT/USD`). The
registry maps `(exchange, canonical) -> native_symbol`; strategies and
storage only ever see the canonical `BASE-QUOTE` form. Survivorship-safe:
delisting a symbol flips `active=False` and stamps `delisted_at` — it is
never removed from the registry.
"""

from __future__ import annotations

from datetime import datetime

from lqe.core.types import Symbol, SymbolRecord

__all__ = [
    "SymbolRecord",
    "SymbolRegistry",
    "from_ccxt_symbol",
    "to_ccxt_symbol",
]


def to_ccxt_symbol(canonical: Symbol) -> str:
    """Default `BASE-QUOTE` -> `BASE/QUOTE` conversion (ccxt's convention)."""
    return canonical.replace("-", "/")


def from_ccxt_symbol(native: str) -> Symbol:
    return native.replace("/", "-").upper()


class SymbolRegistry:
    def __init__(self) -> None:
        self._records: dict[tuple[str, Symbol], SymbolRecord] = {}

    def register(self, record: SymbolRecord) -> None:
        self._records[(record.exchange, record.canonical)] = record

    def get(self, exchange: str, canonical: Symbol) -> SymbolRecord:
        try:
            return self._records[(exchange, canonical)]
        except KeyError:
            raise KeyError(f"{canonical!r} is not registered for exchange {exchange!r}") from None

    def native_symbol(self, exchange: str, canonical: Symbol) -> str:
        return self.get(exchange, canonical).native_symbol

    def delist(self, exchange: str, canonical: Symbol, *, delisted_at: datetime) -> None:
        record = self.get(exchange, canonical)
        self._records[(exchange, canonical)] = record.model_copy(
            update={"active": False, "delisted_at": delisted_at}
        )

    def all(self) -> list[SymbolRecord]:
        return list(self._records.values())
