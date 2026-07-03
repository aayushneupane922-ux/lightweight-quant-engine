from datetime import UTC, datetime

from lqe.core.engine import AuditLog
from lqe.core.events import ControlEvent

SIM_TS = datetime(2026, 1, 1, tzinfo=UTC)


def _build_log() -> AuditLog:
    log = AuditLog()
    log.append(
        event_type="ControlEvent",
        run_id="run-1",
        seq=1,
        book="sandbox",
        sim_ts=SIM_TS,
        payload=ControlEvent(command="START", source="test", operator="tester"),
    )
    log.append(
        event_type="ControlEvent",
        run_id="run-1",
        seq=2,
        book="sandbox",
        sim_ts=SIM_TS,
        payload=ControlEvent(command="STOP", source="test", operator="tester"),
    )
    return log


def test_hash_chain_verifies() -> None:
    log = _build_log()
    assert log.verify() is True
    assert log.head_hash == log.records[-1].hash


def test_hash_chain_detects_tampered_hash() -> None:
    log = _build_log()
    records = log.records
    records[0] = records[0].model_copy(update={"hash": "0" * 64})
    log._records = records  # white-box tamper for the test
    assert log.verify() is False


def test_hash_chain_detects_tampered_payload() -> None:
    log = _build_log()
    records = log.records
    records[1] = records[1].model_copy(update={"payload": {**records[1].payload, "note": "hacked"}})
    log._records = records
    assert log.verify() is False
