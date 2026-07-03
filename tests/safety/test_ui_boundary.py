"""The UI/viz layer is read-only + control-command only (docs/11 §11.1,
§11.12): it must import no `risk`/`execution`/`autonomy` internals and
construct no `Order`. Enforced by static AST scan so a future edit that
reaches past the boundary fails the build, not just review.

The one allowed composition seam is `ui/builder.py`, which the CLI invokes
to wire the catalog in; even it only touches read/registry/control code,
never execution or `make_order`. `live.control` is the sanctioned write
path and is explicitly permitted.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "lqe"
UI_ROOTS = [SRC_ROOT / "ui", SRC_ROOT / "viz3d"]

# Packages the render/read layer must never reach into. `live` as a whole
# is off-limits *except* the sanctioned `live.control` write seam.
FORBIDDEN_PREFIXES = ("lqe.risk", "lqe.execution", "lqe.autonomy")
FORBIDDEN_EXACT = {"lqe.risk", "lqe.execution", "lqe.autonomy"}
ALLOWED_LIVE = {"lqe.live.control"}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def _ui_files() -> list[Path]:
    files: list[Path] = []
    for root in UI_ROOTS:
        if root.exists():
            files.extend(root.rglob("*.py"))
    return files


def test_ui_imports_no_risk_execution_or_autonomy_internals() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _ui_files():
        for mod in _imported_modules(path):
            if mod in ALLOWED_LIVE:
                continue
            if mod in FORBIDDEN_EXACT or mod.startswith(tuple(p + "." for p in FORBIDDEN_PREFIXES)):
                offenders.append((str(path.relative_to(SRC_ROOT)), mod))
    assert not offenders, f"UI reached past its boundary: {offenders}"


def test_ui_constructs_no_order() -> None:
    offenders: list[str] = []
    for path in _ui_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
            if name == "Order":
                offenders.append(str(path.relative_to(SRC_ROOT)))
    assert not offenders, f"UI constructs Order directly: {offenders}"


def test_ui_builder_is_the_only_ui_file_that_imports_models() -> None:
    # docs/11 §11.1: the render layer (app/data) must not import `models`;
    # only the composition seam `ui/builder.py` may, since the CLI drives it.
    for path in (SRC_ROOT / "ui").rglob("*.py"):
        if path.name == "builder.py":
            continue
        mods = _imported_modules(path)
        assert not any(m.startswith("lqe.models") for m in mods), (
            f"{path.name} imports models; only ui/builder.py may"
        )
