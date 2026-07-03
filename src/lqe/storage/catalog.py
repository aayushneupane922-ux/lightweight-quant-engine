"""DuckDB catalog: data versions + the symbol registry (docs/11 §11.4).

The Parquet files are the data; this catalog is the provenance ledger on
top of them — one row per ingest (`data_versions`) and the canonical symbol
registry mirrored for querying. `audit`/`experiments`/`trials`/`promotions`/
`daily_reports` tables join this catalog as M4/M8 need them.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

import duckdb

from lqe.core.types import SymbolRecord


class Catalog:
    def __init__(self, path: str | Path) -> None:
        self._con = duckdb.connect(str(path))
        self._create_tables()

    def _create_tables(self) -> None:
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS data_versions (
                version_id VARCHAR PRIMARY KEY,
                exchange VARCHAR,
                symbol VARCHAR,
                timeframe VARCHAR,
                path VARCHAR,
                rows BIGINT,
                checksum VARCHAR,
                fetched_at TIMESTAMP,
                validated BOOLEAN,
                report VARCHAR
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS symbols (
                canonical VARCHAR,
                exchange VARCHAR,
                native_symbol VARCHAR,
                base VARCHAR,
                quote VARCHAR,
                active BOOLEAN,
                listed_at TIMESTAMP,
                delisted_at TIMESTAMP,
                PRIMARY KEY (canonical, exchange)
            )
            """
        )

    def record_data_version(
        self,
        *,
        version_id: str,
        exchange: str,
        symbol: str,
        timeframe: str,
        path: str,
        rows: int,
        checksum: str,
        fetched_at: datetime,
        validated: bool,
        report: dict[str, Any],
    ) -> None:
        self._con.execute(
            """
            INSERT OR REPLACE INTO data_versions
                (version_id, exchange, symbol, timeframe, path, rows, checksum,
                 fetched_at, validated, report)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                version_id,
                exchange,
                symbol,
                timeframe,
                path,
                rows,
                checksum,
                fetched_at,
                validated,
                json.dumps(report),
            ],
        )

    def upsert_symbol(self, record: SymbolRecord) -> None:
        self._con.execute(
            """
            INSERT OR REPLACE INTO symbols
                (canonical, exchange, native_symbol, base, quote, active, listed_at, delisted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record.canonical,
                record.exchange,
                record.native_symbol,
                record.base,
                record.quote,
                record.active,
                record.listed_at,
                record.delisted_at,
            ],
        )

    def data_versions(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._con.execute(
            "SELECT * FROM data_versions ORDER BY fetched_at"
        ).to_arrow_table().to_pylist()
        return result

    def symbols(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._con.execute(
            "SELECT * FROM symbols ORDER BY canonical"
        ).to_arrow_table().to_pylist()
        return result

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """The open connection, so sibling tables (analytics/registry.py's
        experiments/trials) can live in the same catalog.duckdb file without
        each module opening its own competing file handle."""
        return self._con

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> Catalog:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
