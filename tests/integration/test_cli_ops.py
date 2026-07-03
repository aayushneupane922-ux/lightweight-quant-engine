"""M12 CLI polish: a missing bundle prints a clean error (not a traceback)
with a non-zero exit; `lqe doctor` and `lqe backup` run end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lqe.cli import main

Capsys = pytest.CaptureFixture[str]


def test_backtest_missing_bundle_is_clean_error(tmp_path: Path, capsys: Capsys) -> None:
    exit_code = main(
        ["backtest", "--bundle", "nope", "--root", str(tmp_path / "data"), "--symbol", "BTC-USDT"]
    )
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "error:" in out
    assert "not found" in out
    assert "Traceback" not in out


def test_autopilot_missing_bundle_is_clean_error(tmp_path: Path, capsys: Capsys) -> None:
    exit_code = main(
        ["autopilot", "--bundle", "nope", "--root", str(tmp_path / "runs"), "--symbol", "BTC-USDT"]
    )
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "error:" in out and "not found" in out


def test_doctor_runs_and_exits_zero(capsys: Capsys) -> None:
    exit_code = main(["doctor", "--no-license"])
    out = capsys.readouterr().out
    assert exit_code == 0  # WARNs (no audit/kill inputs) still exit 0
    assert "paper-only lockout" in out
    assert "overall:" in out
    out.encode("ascii")  # ASCII-only report


def test_doctor_fails_on_tampered_audit(tmp_path: Path, capsys: Capsys) -> None:
    from datetime import UTC, datetime

    from lqe.core.engine import AuditLog
    from lqe.core.events import ControlEvent

    log = AuditLog()
    log.append(
        event_type="ControlEvent", run_id="r", seq=0, book="sandbox",
        sim_ts=datetime(2026, 1, 1, tzinfo=UTC),
        payload=ControlEvent(command="START", source="t", operator="t", note="keep"),
    )
    audit = tmp_path / "audit.jsonl"
    log.write_jsonl(audit)
    audit.write_text(audit.read_text(encoding="utf-8").replace("keep", "hack"), encoding="utf-8")

    exit_code = main(["doctor", "--no-license", "--audit", str(audit)])
    assert exit_code == 1
    assert "FAIL" in capsys.readouterr().out


def test_backup_cli(tmp_path: Path, capsys: Capsys) -> None:
    (tmp_path / "catalog.duckdb").write_bytes(b"db")
    exit_code = main(["backup", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "backup ->" in out
    assert list((tmp_path / "backups").glob("lqe-backup-*.zip"))
