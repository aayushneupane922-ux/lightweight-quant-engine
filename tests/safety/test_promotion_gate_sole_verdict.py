"""Only `PromotionGate.check` may construct a `GateResult` — the same
discipline as `make_order` (docs/11 §11.6: "only Validator/PromotionGate
may construct this; Narrator/LLM cannot set verdict"). AST scan of
`src/lqe`, mirroring `tests/safety/test_make_order_lockout.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "lqe"
ALLOWED_FILE = SRC_ROOT / "autonomy" / "promotion_gate.py"


def _calls_gate_result_constructor(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
        if name == "GateResult":
            return True
    return False


def test_gate_result_is_only_constructed_by_the_promotion_gate() -> None:
    offenders = [
        path
        for path in SRC_ROOT.rglob("*.py")
        if path != ALLOWED_FILE and _calls_gate_result_constructor(path)
    ]
    assert offenders == [], f"GateResult() constructed outside promotion_gate.py in: {offenders}"


def test_gate_result_verdict_is_a_closed_literal() -> None:
    """Belt-and-braces: even if something did construct a GateResult, the
    verdict field only accepts PASS/FAIL — nothing else, no free-text."""
    from lqe.autonomy.promotion_gate import GateResult

    assert GateResult.model_fields["verdict"].annotation is not None
    schema = GateResult.model_json_schema()
    assert set(schema["properties"]["verdict"]["enum"]) == {"PASS", "FAIL"}
