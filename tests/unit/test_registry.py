"""docs/10 M4: trial count spans all trials/models — the honest count that
feeds DSR/PBO is a query over every recorded trial, not a per-model tally
someone has to remember to sum.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lqe.analytics.registry import ExperimentRegistry
from lqe.storage.catalog import Catalog

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_trial_count_spans_multiple_models(tmp_path: Path) -> None:
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        registry = ExperimentRegistry(catalog)

        registry.record_experiment(
            run_id="run-a", mode="backtest", book="sandbox", strategy="trend_ma_cross",
            params={"fast": 12, "slow": 48}, data_version="dv-1", git_sha="abc123", seed=1,
            date_start=NOW, date_end=NOW, split="test", sharpe=0.5, dsr=0.6, pbo=0.2,
            max_dd=0.1, turnover=1.0, n_trades=50, cost_bps=10.0, passed_gate=False,
            created_at=NOW,
        )
        registry.record_experiment(
            run_id="run-b", mode="backtest", book="sandbox", strategy="meanrev_zscore",
            params={"window": 20}, data_version="dv-1", git_sha="abc123", seed=2,
            date_start=NOW, date_end=NOW, split="test", sharpe=0.8, dsr=0.9, pbo=0.1,
            max_dd=0.05, turnover=2.0, n_trades=80, cost_bps=10.0, passed_gate=True,
            created_at=NOW,
        )

        for idx, run_id in enumerate(["run-a", "run-b"]):
            for trial_idx in range(3):
                registry.record_trial(
                    trial_id=f"{run_id}-trial-{trial_idx}", run_id=run_id, study_id=f"study-{idx}",
                    hypo_id=f"H-{idx}", params={"idx": trial_idx}, oos_metric=0.1 * trial_idx,
                    seed=trial_idx, idx=trial_idx, created_at=NOW,
                )

        # spans BOTH models' trials, not just one
        assert registry.trial_count() == 6
        assert registry.trial_count(data_version="dv-1") == 6
        assert registry.trial_count(data_version="nonexistent") == 0

        experiments = registry.experiments()
        assert {e["strategy"] for e in experiments} == {"trend_ma_cross", "meanrev_zscore"}
        trials = registry.trials()
        assert {t["run_id"] for t in trials} == {"run-a", "run-b"}


def test_registry_shares_the_catalog_connection(tmp_path: Path) -> None:
    with Catalog(tmp_path / "catalog.duckdb") as catalog:
        registry = ExperimentRegistry(catalog)
        assert registry._con is catalog.connection  # same open handle, no file-lock contention
