"""`lqe backup` snapshots (docs/10 M12). Read-only w.r.t. sources; missing
sources are skipped, not an error; the archive never swallows its own dest.
"""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

from lqe.ops.backup import create_backup


def _seed(root: Path) -> None:
    (root / "data" / "curated").mkdir(parents=True)
    (root / "data" / "curated" / "bars.parquet").write_bytes(b"bar-bytes")
    (root / "runs").mkdir()
    (root / "runs" / "audit.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "catalog.duckdb").write_bytes(b"db")


def test_backup_archives_existing_sources(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = create_backup(tmp_path, now=datetime(2026, 7, 3, 12, tzinfo=UTC))

    assert result.archive.exists()
    assert result.archive.name == "lqe-backup-20260703T120000Z.zip"
    assert set(result.included) == {"data", "runs", "catalog.duckdb"}
    assert result.files == 3
    with zipfile.ZipFile(result.archive) as zf:
        names = set(zf.namelist())
    assert "data/curated/bars.parquet" in names
    assert "catalog.duckdb" in names


def test_backup_skips_absent_sources(tmp_path: Path) -> None:
    (tmp_path / "catalog.duckdb").write_bytes(b"db")  # only the catalog exists
    result = create_backup(tmp_path)

    assert result.included == ["catalog.duckdb"]
    assert set(result.skipped) == {"data", "runs"}
    assert result.files == 1


def test_backup_leaves_sources_untouched(tmp_path: Path) -> None:
    _seed(tmp_path)
    before = (tmp_path / "catalog.duckdb").read_bytes()
    create_backup(tmp_path)
    assert (tmp_path / "catalog.duckdb").read_bytes() == before
    assert (tmp_path / "data" / "curated" / "bars.parquet").exists()


def test_backup_does_not_recurse_into_its_own_dest(tmp_path: Path) -> None:
    _seed(tmp_path)
    # Point dest inside a backed-up source; that source must be skipped so the
    # archive can't fold itself in and grow unboundedly.
    dest = tmp_path / "runs" / "backups"
    result = create_backup(tmp_path, dest_dir=dest)
    assert "runs" in result.skipped
