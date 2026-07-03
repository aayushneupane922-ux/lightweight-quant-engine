"""Module-layering guardrails (docs/11 §11.1), enforced by static AST scan
so a future edit that crosses a boundary fails the build, not just review.

Focus of these checks: keep the low layers acyclic and dependency-light.
`core` depends on nothing project-specific; `storage` and `data` never
import *each other* (the data↔storage mutual dependency fixed post-M10) —
the one sanctioned cross is `data.ingest → storage`, the pipeline that
persists curated bars.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "lqe"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def _pkg_imports(package: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for path in (SRC_ROOT / package).rglob("*.py"):
        out[str(path.relative_to(SRC_ROOT))] = _imported_modules(path)
    return out


def test_core_imports_nothing_project_specific() -> None:
    for name, mods in _pkg_imports("core").items():
        leaks = [m for m in mods if m.startswith("lqe.") and not m.startswith("lqe.core")]
        assert not leaks, f"{name} imports outside core: {leaks}"


def test_storage_never_imports_data() -> None:
    for name, mods in _pkg_imports("storage").items():
        assert not any(m.startswith("lqe.data") for m in mods), f"{name} imports data"


def test_storage_imports_only_core() -> None:
    for name, mods in _pkg_imports("storage").items():
        leaks = [
            m for m in mods
            if m.startswith("lqe.") and not m.startswith(("lqe.core", "lqe.storage"))
        ]
        assert not leaks, f"{name} imports outside core/storage: {leaks}"


def test_data_only_crosses_to_storage_via_the_ingest_pipeline() -> None:
    # `data` may reach `storage` only from ingest.py (persisting curated
    # bars); the market-data adapters/registry must not depend on storage.
    for name, mods in _pkg_imports("data").items():
        if name.endswith("ingest.py"):
            continue
        assert not any(m.startswith("lqe.storage") for m in mods), f"{name} imports storage"
