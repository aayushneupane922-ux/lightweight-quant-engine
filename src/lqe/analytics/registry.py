"""The experiment/trial registry (docs/11 §11.4): one row per run, one row
per trial. This is what makes trial-counting automatic and honest —
`n_trials` for DSR/PBO is a query over this table, not a number someone
remembers to track by hand (docs/archive/09 §9.10).

Lives in the same `catalog.duckdb` file as `storage.catalog.Catalog`
(reuses its open connection) — different tables, one provenance database.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import duckdb

from lqe.storage.catalog import Catalog


class ExperimentRegistry:
    def __init__(self, catalog: Catalog) -> None:
        self._con: duckdb.DuckDBPyConnection = catalog.connection
        self._create_tables()

    def _create_tables(self) -> None:
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                run_id VARCHAR PRIMARY KEY,
                mode VARCHAR,
                book VARCHAR,
                strategy VARCHAR,
                params VARCHAR,
                data_version VARCHAR,
                git_sha VARCHAR,
                seed BIGINT,
                date_start TIMESTAMP,
                date_end TIMESTAMP,
                split VARCHAR,
                sharpe DOUBLE,
                dsr DOUBLE,
                pbo DOUBLE,
                max_dd DOUBLE,
                turnover DOUBLE,
                n_trades BIGINT,
                cost_bps DOUBLE,
                passed_gate BOOLEAN,
                created_at TIMESTAMP,
                notes VARCHAR
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS trials (
                trial_id VARCHAR PRIMARY KEY,
                run_id VARCHAR,
                study_id VARCHAR,
                hypo_id VARCHAR,
                params VARCHAR,
                oos_metric DOUBLE,
                seed BIGINT,
                idx BIGINT,
                created_at TIMESTAMP
            )
            """
        )

    def record_experiment(
        self,
        *,
        run_id: str,
        mode: str,
        book: str,
        strategy: str,
        params: dict[str, Any],
        data_version: str,
        git_sha: str,
        seed: int,
        date_start: datetime,
        date_end: datetime,
        split: str,
        sharpe: float,
        dsr: float,
        pbo: float,
        max_dd: float,
        turnover: float,
        n_trades: int,
        cost_bps: float,
        passed_gate: bool,
        created_at: datetime,
        notes: str = "",
    ) -> None:
        self._con.execute(
            """
            INSERT OR REPLACE INTO experiments
                (run_id, mode, book, strategy, params, data_version, git_sha, seed,
                 date_start, date_end, split, sharpe, dsr, pbo, max_dd, turnover,
                 n_trades, cost_bps, passed_gate, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id, mode, book, strategy, json.dumps(params), data_version, git_sha, seed,
                date_start, date_end, split, sharpe, dsr, pbo, max_dd, turnover,
                n_trades, cost_bps, passed_gate, created_at, notes,
            ],
        )

    def record_trial(
        self,
        *,
        trial_id: str,
        run_id: str,
        study_id: str,
        hypo_id: str,
        params: dict[str, Any],
        oos_metric: float,
        seed: int,
        idx: int,
        created_at: datetime,
    ) -> None:
        self._con.execute(
            """
            INSERT OR REPLACE INTO trials
                (trial_id, run_id, study_id, hypo_id, params, oos_metric, seed, idx, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                trial_id, run_id, study_id, hypo_id, json.dumps(params),
                oos_metric, seed, idx, created_at,
            ],
        )

    def experiments(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._con.execute(
            "SELECT * FROM experiments ORDER BY created_at"
        ).to_arrow_table().to_pylist()
        return result

    def trials(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._con.execute(
            "SELECT * FROM trials ORDER BY created_at"
        ).to_arrow_table().to_pylist()
        return result

    def trial_count(self, *, data_version: str | None = None) -> int:
        """The honest trial count that feeds DSR/PBO (docs/04 §4.2): every
        trial recorded, optionally scoped to one data version."""
        if data_version is None:
            row = self._con.execute("SELECT count(*) FROM trials").fetchone()
        else:
            row = self._con.execute(
                """
                SELECT count(*) FROM trials t
                JOIN experiments e ON t.run_id = e.run_id
                WHERE e.data_version = ?
                """,
                [data_version],
            ).fetchone()
        return int(row[0]) if row else 0
