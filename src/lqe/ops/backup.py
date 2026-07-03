"""`lqe backup` — snapshot the local research state (docs/10 M12).

Zips whatever of `data/`, `runs/`, and `catalog.duckdb` exists into a single
timestamped archive under a backup directory. Read-only with respect to the
sources; the archive name is deterministic-per-timestamp so repeated runs don't
clobber. Pure stdlib (`zipfile`), no new dependency.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# The local state worth preserving. Relative to the working root; each may or
# may not exist depending on how far the user has driven the engine.
DEFAULT_SOURCES = ("data", "runs", "catalog.duckdb")


@dataclass(frozen=True)
class BackupResult:
    archive: Path
    files: int
    bytes_total: int
    included: list[str]
    skipped: list[str]


def _iter_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*") if p.is_file())


def create_backup(
    root: Path,
    *,
    dest_dir: Path | None = None,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    now: datetime | None = None,
) -> BackupResult:
    """Zip the existing `sources` (relative to `root`) into
    `dest_dir/lqe-backup-<UTC timestamp>.zip`. Missing sources are skipped, not
    an error — a fresh install has no `runs/` yet."""
    root = root.resolve()
    dest_dir = (dest_dir or root / "backups").resolve()
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / f"lqe-backup-{stamp}.zip"

    included: list[str] = []
    skipped: list[str] = []
    file_count = 0
    bytes_total = 0

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for source in sources:
            src = (root / source).resolve()
            # Skip a source that doesn't exist, or one that *contains* the
            # backup destination — otherwise the archive (written under
            # dest_dir) would fold itself in and grow unboundedly.
            if not src.exists() or src == dest_dir or src in dest_dir.parents:
                skipped.append(source)
                continue
            included.append(source)
            for file in _iter_files(src):
                arcname = file.relative_to(root).as_posix()
                zf.write(file, arcname)
                file_count += 1
                bytes_total += file.stat().st_size

    return BackupResult(
        archive=archive,
        files=file_count,
        bytes_total=bytes_total,
        included=included,
        skipped=skipped,
    )
