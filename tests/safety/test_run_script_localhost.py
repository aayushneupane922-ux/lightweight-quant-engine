"""The local launcher (`run.py`) must stay loopback-only (docs/10 M12).

Both entry points (`lqe desk` and `run.py`) delegate binding to
`ui.app.serve`, which hard-codes `BIND_HOST = 127.0.0.1`. This test guards
`run.py` against ever hard-coding a routable bind address (`0.0.0.0`, a LAN
IP, etc.) — the desk has no auth precisely because it is unreachable off the
loopback interface.
"""

from __future__ import annotations

from pathlib import Path

_RUN_PY = Path(__file__).resolve().parents[2] / "run.py"

# Any of these appearing as a literal in run.py would expose the desk beyond
# the loopback interface.
_FORBIDDEN = ("0.0.0.0", "::", "host=", "0:0:0:0")


def test_run_py_exists() -> None:
    assert _RUN_PY.exists(), "run.py launcher is missing"


def test_run_py_has_no_routable_bind_literal() -> None:
    text = _RUN_PY.read_text(encoding="utf-8")
    for needle in _FORBIDDEN:
        assert needle not in text, f"run.py references {needle!r} — must bind loopback only"


def test_run_py_url_is_built_from_bind_host() -> None:
    # The printed/opened URL must be derived from ui.app.BIND_HOST, not a
    # separately-typed address that could drift from the real bind.
    text = _RUN_PY.read_text(encoding="utf-8")
    assert "BIND_HOST" in text
    from lqe.ui.app import BIND_HOST

    assert BIND_HOST == "127.0.0.1"
