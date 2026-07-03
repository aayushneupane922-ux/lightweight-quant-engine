"""`lqe doctor` — a one-command health check for the local install
(docs/10 M12).

Every check is a pure function of its inputs returning a `Check`; the command
layer only formats them. The check set is the standing safety/honesty gate in
runnable form: paper-only lockout intact, config rejects live, the audit chain
(if a log is supplied) verifies, the kill switch state is reported, the catalog
still builds, and — optionally — the license gate passes. Nothing here can
change state; `doctor` is read-only.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Status = Literal["OK", "WARN", "FAIL"]


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


def _paper_only_check() -> Check:
    from lqe import constants
    from lqe.core.config import assert_paper_only
    from lqe.core.errors import LockoutViolation
    from lqe.execution.paper_broker import PaperBroker

    if constants.LIVE_TRADING_ENABLED is not False:
        return Check("paper-only lockout", "FAIL", "LIVE_TRADING_ENABLED is not False")
    if not PaperBroker.is_paper:
        return Check("paper-only lockout", "FAIL", "PaperBroker.is_paper is not True")
    # The startup assertion must reject a non-paper adapter.
    try:
        assert_paper_only(False)
    except LockoutViolation:
        pass
    else:
        return Check("paper-only lockout", "FAIL", "assert_paper_only(False) did not raise")
    return Check(
        "paper-only lockout",
        "OK",
        "LIVE_TRADING_ENABLED=False, PaperBroker.is_paper=True, startup assert rejects live",
    )


def _config_lockout_check() -> Check:
    from lqe.core.config import Config
    from lqe.core.errors import LockoutViolation

    live = {
        "engine": {
            "mode": "live",
            "clock": "wallclock",
            "seed": 0,
            "base_currency": "USDT",
            "starting_cash": "10000",
        },
        "execution": {"adapter": "paper"},
        "data": {
            "adapter": "ccxt",
            "exchange": "binance",
            "symbols": ["BTC-USDT"],
            "timeframe": "1m",
        },
    }
    try:
        Config.from_dict(live)
    except LockoutViolation:
        return Check("config lockout", "OK", "a config with mode=live is refused by name")
    except Exception as exc:  # noqa: BLE001 - any refusal is acceptable; a *pass* is the bug
        return Check("config lockout", "OK", f"live config rejected ({type(exc).__name__})")
    return Check("config lockout", "FAIL", "a config with mode=live was accepted")


def _audit_check(audit_path: Path | None) -> Check:
    from lqe.core.engine import AuditLog

    if audit_path is None:
        return Check("audit hash-chain", "WARN", "no --audit log supplied; skipped")
    if not audit_path.exists():
        return Check("audit hash-chain", "FAIL", f"audit log not found: {audit_path}")
    try:
        log = AuditLog.from_jsonl(audit_path)
    except Exception as exc:  # noqa: BLE001 - from_jsonl raises on a tampered/truncated log
        return Check("audit hash-chain", "FAIL", f"{audit_path.name}: {exc}")
    return Check("audit hash-chain", "OK", f"{audit_path.name}: {len(log.records)} records verify")


def _kill_switch_check(kill_switch_path: Path | None) -> Check:
    from lqe.risk.kill_switch import KillSwitch

    if kill_switch_path is None:
        return Check("kill switch", "WARN", "no --kill-switch path; nothing persisted to inspect")
    ks = KillSwitch(kill_switch_path)
    if ks.active:
        return Check(
            "kill switch",
            "WARN",
            f"ACTIVE — the book is halted (reason: {ks.reason or 'unspecified'})",
        )
    return Check("kill switch", "OK", f"clear (file: {kill_switch_path})")


def _catalog_check(symbol: str) -> Check:
    from lqe.models.catalog_scale import build_scaled_catalog

    try:
        catalog, results = build_scaled_catalog(symbol)
    except Exception as exc:  # noqa: BLE001 - report a build failure rather than crash doctor
        return Check("model catalog", "FAIL", f"build_scaled_catalog raised: {exc}")
    admitted = len(catalog.all())
    quarantined = len(catalog.quarantined())
    if admitted == 0:
        return Check("model catalog", "FAIL", "no models admitted")
    return Check(
        "model catalog",
        "OK",
        f"{len(results)} registered: {admitted} admitted, {quarantined} transparently quarantined",
    )


def _license_check() -> Check:
    """Run the standing license gate in a subprocess. Fails closed on a DENY/
    REVIEW; degrades to WARN (not FAIL) only when the auditing tool itself
    (`pip-licenses`) isn't installed, so `doctor` stays runnable in a minimal
    env while never green-lighting an unvetted license."""
    script = Path(__file__).resolve().parents[3] / "scripts" / "license_gate.py"
    if not script.exists():
        return Check("license gate", "WARN", f"gate script not found at {script}")
    try:
        completed = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001 - surface any launch failure as WARN
        return Check("license gate", "WARN", f"could not run gate: {exc}")
    out = (completed.stdout + completed.stderr).strip().splitlines()
    tail = out[-1] if out else "(no output)"
    if completed.returncode == 0:
        return Check("license gate", "OK", tail)
    if "piplicenses" in (completed.stderr or "") or "pip-licenses" in (completed.stderr or ""):
        return Check("license gate", "WARN", "pip-licenses not installed; gate not run")
    return Check("license gate", "FAIL", tail)


def run_health_checks(
    *,
    audit_path: Path | None = None,
    kill_switch_path: Path | None = None,
    symbol: str = "BTC-USDT",
    run_license_gate: bool = True,
) -> list[Check]:
    """The full doctor sweep. Ordered safety-first; the license gate is last
    because it shells out and is the slowest."""
    checks = [
        _paper_only_check(),
        _config_lockout_check(),
        _audit_check(audit_path),
        _kill_switch_check(kill_switch_path),
        _catalog_check(symbol),
    ]
    if run_license_gate:
        checks.append(_license_check())
    return checks


def format_report(checks: list[Check]) -> str:
    """ASCII-only so it renders on every console (Windows cp1252 included)."""
    width = max((len(c.name) for c in checks), default=0)
    lines = [f"  [{c.status:>4}] {c.name.ljust(width)}  {c.detail}" for c in checks]
    return "\n".join(lines)


def worst_status(checks: list[Check]) -> Status:
    if any(c.status == "FAIL" for c in checks):
        return "FAIL"
    if any(c.status == "WARN" for c in checks):
        return "WARN"
    return "OK"
