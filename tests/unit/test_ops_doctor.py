"""`lqe doctor` health checks (docs/10 M12). Doctor is read-only and its
verdict maps cleanly to an exit code: any FAIL is a broken invariant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lqe.core.engine import AuditLog
from lqe.core.events import ControlEvent
from lqe.ops.health import format_report, run_health_checks, worst_status
from lqe.risk.kill_switch import KillSwitch

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _write_audit(path: Path, *, note: str = "hello") -> None:
    log = AuditLog()
    log.append(
        event_type="ControlEvent", run_id="doctor-test", seq=0, book="sandbox", sim_ts=NOW,
        payload=ControlEvent(command="START", source="test", operator="tester", note=note),
    )
    log.write_jsonl(path)


def test_doctor_core_checks_pass_without_optional_inputs() -> None:
    checks = run_health_checks(run_license_gate=False)
    by_name = {c.name: c for c in checks}
    # The structural safety invariants must be OK on a healthy tree.
    assert by_name["paper-only lockout"].status == "OK"
    assert by_name["config lockout"].status == "OK"
    assert by_name["model catalog"].status == "OK"
    # Absent optional inputs are WARN (informational), never FAIL.
    assert by_name["audit hash-chain"].status == "WARN"
    assert by_name["kill switch"].status == "WARN"
    assert worst_status(checks) != "FAIL"


def test_doctor_verifies_a_real_audit_log(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.jsonl"
    _write_audit(log_path)

    checks = run_health_checks(audit_path=log_path, run_license_gate=False)
    audit = next(c for c in checks if c.name == "audit hash-chain")
    assert audit.status == "OK"
    assert "verify" in audit.detail


def test_doctor_flags_a_tampered_audit_log(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.jsonl"
    _write_audit(log_path, note="hello")
    # Corrupt the payload so the hash chain no longer verifies.
    text = log_path.read_text(encoding="utf-8").replace("hello", "tampered")
    log_path.write_text(text, encoding="utf-8")

    checks = run_health_checks(audit_path=log_path, run_license_gate=False)
    audit = next(c for c in checks if c.name == "audit hash-chain")
    assert audit.status == "FAIL"
    assert worst_status(checks) == "FAIL"


def test_doctor_reports_active_kill_switch(tmp_path: Path) -> None:
    ks_path = tmp_path / "kill.json"
    KillSwitch(ks_path).trigger(reason="operator halt")

    checks = run_health_checks(kill_switch_path=ks_path, run_license_gate=False)
    ks = next(c for c in checks if c.name == "kill switch")
    assert ks.status == "WARN"
    assert "operator halt" in ks.detail


def test_doctor_reports_clear_kill_switch(tmp_path: Path) -> None:
    ks_path = tmp_path / "kill.json"
    ks = KillSwitch(ks_path)
    ks.trigger(reason="x")
    ks.clear(operator="alice")

    checks = run_health_checks(kill_switch_path=ks_path, run_license_gate=False)
    entry = next(c for c in checks if c.name == "kill switch")
    assert entry.status == "OK"


def test_format_report_is_ascii_only() -> None:
    checks = run_health_checks(run_license_gate=False)
    report = format_report(checks)
    report.encode("ascii")  # must not raise — renders on cp1252 consoles


def test_doctor_ollama_check_is_informational_never_fail() -> None:
    """docs/12 M17: Ollama absent is a fully supported state (rule-based
    fallback, docs/10 M9) -- this check must never be able to FAIL the
    whole doctor sweep regardless of whether a server happens to be up."""
    checks = run_health_checks(run_license_gate=False)
    ollama = next(c for c in checks if c.name == "local LLM (Ollama)")
    assert ollama.status in ("OK", "WARN")
