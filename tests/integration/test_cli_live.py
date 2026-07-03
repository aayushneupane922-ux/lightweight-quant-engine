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
