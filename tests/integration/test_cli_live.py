"""`lqe live` end-to-end (docs/12 M14): the post-v1.0 live-fleet extension
(originally `scripts/run_live_fleet.py`) ported into the tagged CLI. Uses
`--adapter csv` (a local fixture, not a real exchange) so this runs offline
and deterministically in CI -- the same offline-adapter seam `lqe ingest`
already exposes via `--adapter csv`.

The fixture's timestamps are generated relative to real wall-clock `now`
(not a fixed past date) because `LiveFeed.seed_history`/`poll_new_bars` filter
by "closed relative to now" using the real clock by default -- a fixed
2026-01-01 fixture would fall outside the seed window and seed zero bars.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lqe.cli import main
from lqe.core.engine import AuditLog

pytest.importorskip("fastapi")
pytest.importorskip("optuna")

SYMBOL = "BTC-USDT"
N_BARS = 150


def _fixture_csv(tmp_path: Path) -> Path:
    now = datetime.now(UTC)
    rows = ["ts_open,open,high,low,close,volume"]
    price = 100.0
    for i in range(N_BARS):
        # Newest bar 5 minutes before "now" -- comfortably closed for a 1m
        # timeframe (LiveFeed only requires >=60s), oldest bar N_BARS+5 back.
        ts = now - timedelta(minutes=(N_BARS - i) + 5)
        drift = 0.01 * i
        close = 100.0 + drift
        openp = price
        high = max(openp, close) + 0.5
        low = min(openp, close) - 0.5
        rows.append(
            f"{ts.isoformat()},{openp:.2f},{high:.2f},{low:.2f},{close:.2f},{10 + (i % 5)}"
        )
        price = close
    path = tmp_path / "live_fixture.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_lqe_live_help_lists_the_ported_flags() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["live", "--help"])
    assert exc.value.code == 0


def test_lqe_live_runs_bounded_against_a_csv_fixture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv_path = _fixture_csv(tmp_path)

    exit_code = main(
        [
            "live",
            "--adapter", "csv",
            "--csv-path", str(csv_path),
            "--exchange", "demo",
            "--symbol", SYMBOL,
            "--timeframe", "1m",
            "--lookback-bars", "100",
            "--poll-seconds", "0",
            "--max-polls", "2",
            "--min-periods", "50",
            "--n-trials", "1",
            "--autonomy-every", "1000",  # high enough that no autonomy step fires
            "--kill-switch", str(tmp_path / "kill.json"),
            "--port", "0",  # OS-assigned ephemeral port -- no conflict with other tests
            "--no-browser",
        ]
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "fleet: 51/51 models admitted" in out
    # exact count can be 1-2 off real wall-clock skew between fixture
    # generation and the CLI's own now() check -- assert the shape, not
    # an exact count.
    assert "seeded " in out and " bars, last close=" in out
    assert "no bars returned" not in out
    assert "Obsidian Desk ->" in out


def test_lqe_live_resumes_byte_identical_state_from_the_same_out_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """docs/12 M15: passing the same --out path on a later run must
    reconstruct exactly the state that was there before -- verified here by
    replaying the identical historical bars (the CSV fixture never grows)
    and asserting the persisted trading audit is byte-for-byte identical,
    not just "close enough"."""
    csv_path = _fixture_csv(tmp_path)
    out_path = tmp_path / "live-session.jsonl"

    base_args = [
        "live",
        "--adapter", "csv",
        "--csv-path", str(csv_path),
        "--exchange", "demo",
        "--symbol", SYMBOL,
        "--timeframe", "1m",
        "--lookback-bars", "100",
        "--poll-seconds", "0",
        "--max-polls", "0",  # replay/seed once, persist, no polling iterations
        "--min-periods", "50",
        "--n-trials", "1",
        "--autonomy-every", "1000",
        "--port", "0",
        "--no-browser",
        "--out", str(out_path),
    ]

    exit_code_1 = main(base_args)
    capsys.readouterr()  # discard run 1's stdout
    assert exit_code_1 == 0
    assert out_path.exists()
    # event_id (uuid4) and wall_ts (real clock) are real, non-deterministic
    # metadata excluded from the hash chain by design (core/engine.py) -- so
    # "byte-identical reconstructed state" means identical hash chains, not
    # identical raw file bytes.
    audit_1 = AuditLog.from_jsonl(out_path)
    assert audit_1.verify()

    exit_code_2 = main(base_args)
    out_2 = capsys.readouterr().out
    assert exit_code_2 == 0
    assert "resuming from" in out_2
    audit_2 = AuditLog.from_jsonl(out_path)
    assert audit_2.verify()

    assert audit_2.head_hash == audit_1.head_hash
    assert [r.hash for r in audit_2.records] == [r.hash for r in audit_1.records]
    assert [r.payload for r in audit_2.records] == [r.payload for r in audit_1.records]


def test_lqe_live_a_fresh_out_path_starts_flat(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv_path = _fixture_csv(tmp_path)
    exit_code = main(
        [
            "live",
            "--adapter", "csv",
            "--csv-path", str(csv_path),
            "--symbol", SYMBOL,
            "--lookback-bars", "100",
            "--poll-seconds", "0",
            "--max-polls", "0",
            "--min-periods", "50",
            "--n-trials", "1",
            "--autonomy-every", "1000",
            "--port", "0",
            "--no-browser",
            "--out", str(tmp_path / "brand-new.jsonl"),  # never seen before -> no resume
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "resuming from" not in out
    assert "seeding " in out


def test_lqe_live_requires_csv_path_with_csv_adapter(tmp_path: Path) -> None:
    exit_code = main(
        [
            "live",
            "--adapter", "csv",
            "--symbol", SYMBOL,
            "--port", "0",
            "--no-browser",
            "--max-polls", "0",
        ]
    )
    assert exit_code == 1
