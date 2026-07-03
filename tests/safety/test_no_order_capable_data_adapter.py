"""A `MarketDataAdapter` must never expose a trading method (docs/06 §6.3,
docs/11 §11.2). Grep + AST scan over `src/lqe`, plus a direct check that the
shipped adapters don't define any of these methods.
"""

from __future__ import annotations

import ast
from pathlib import Path

from lqe.data.ccxt_adapter import CcxtMarketDataAdapter
from lqe.data.csv_replay import CsvReplayAdapter

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "lqe"

FORBIDDEN_METHOD_NAMES = {
    "create_order",
    "createOrder",
    "cancel_order",
    "cancelOrder",
    "create_market_order",
    "create_limit_order",
    "withdraw",
}


def _defines_or_calls_forbidden_method(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in FORBIDDEN_METHOD_NAMES:
            hits.append(f"defines {node.name}")
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_METHOD_NAMES:
            hits.append(f"references .{node.attr}")
    return hits


def test_no_trading_method_anywhere_in_src() -> None:
    offenders = {}
    for path in SRC_ROOT.rglob("*.py"):
        hits = _defines_or_calls_forbidden_method(path)
        if hits:
            offenders[str(path)] = hits
    assert offenders == {}, f"trading-capable method found: {offenders}"


def test_ccxt_adapter_has_no_trading_methods() -> None:
    for name in FORBIDDEN_METHOD_NAMES:
        assert not hasattr(CcxtMarketDataAdapter, name)


def test_csv_replay_adapter_has_no_trading_methods() -> None:
    for name in FORBIDDEN_METHOD_NAMES:
        assert not hasattr(CsvReplayAdapter, name)
