"""docs/14 §1/§7 (v4) M23 exit gate: "score computed" must be a genuine,
repeatable capability, not a one-off script run. This runs the exact same
real pipeline as `scripts/diversification_report.py` (build the scaled
catalog -> real multi-symbol `Session` backtests -> per-bar equity returns
-> `diversification_score()`) end-to-end on a small sample, fast enough for
the default suite. The full 94-model sweep over a longer synthetic window
is `scripts/diversification_report.py` itself (a few minutes; not part of
the default test run, same pattern as `make_demo_run.py`).
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from lqe.analytics.diversification import (
    DiversificationScore,
    cross_group_average_correlation,
    diversification_score,
)
from lqe.backtest.runner import run_backtest
from lqe.core.events import MarketEvent
from lqe.core.types import Symbol
from lqe.models.catalog_scale import build_scaled_catalog

# `scripts/` isn't an installed package -- load `_write_artifact` (docs/15
# V5 M29) directly by file path rather than sys.path-hacking it in, so this
# test can pin the exact JSON schema `ui/data.py::DeskData.diversification()`
# reads without re-running the full (multi-minute) catalog sweep in `main()`.
_spec = importlib.util.spec_from_file_location(
    "diversification_report",
    Path(__file__).resolve().parents[2] / "scripts" / "diversification_report.py",
)
assert _spec is not None and _spec.loader is not None
_diversification_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_diversification_report)
_write_artifact = _diversification_report._write_artifact

SYMBOL: Symbol = "BTC-USDT"
PERP_SYMBOL: Symbol = "BTC-USDT-PERP"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _merged_bars(n: int) -> list[MarketEvent]:
    rng = np.random.default_rng(7)
    btc = 100.0 + np.cumsum(rng.normal(0.02, 0.5, n))
    eth = 0.4 * btc + rng.normal(0, 1.0, n) + 40.0
    sol = 0.2 * btc + rng.normal(0, 1.0, n) + 15.0
    perp = btc * 1.008 + rng.normal(0, 0.3, n)
    bars: list[MarketEvent] = []
    for i in range(n):
        ts = START + timedelta(minutes=i)
        for symbol, series in (
            ("ETH-USDT", eth), ("SOL-USDT", sol), (PERP_SYMBOL, perp), (SYMBOL, btc),
        ):
            price = Decimal(str(round(float(series[i]), 4)))
            bars.append(
                MarketEvent(
                    exchange="synthetic", symbol=symbol, timeframe="1m", ts_open=ts,
                    o=price, h=price + Decimal("0.5"), l=price - Decimal("0.5"), c=price,
                    v=100.0, source_version="test",
                )
            )
    return bars


def _bar_returns(equity_curve: list[Decimal]) -> list[float]:
    return [
        float((cur - prev) / prev) if prev != 0 else 0.0
        for prev, cur in zip(equity_curve, equity_curve[1:])  # noqa: B905 - deliberately uneven
    ]


def test_diversification_score_computes_over_real_backtested_returns() -> None:
    bars = _merged_bars(150)
    catalog, _ = build_scaled_catalog(SYMBOL)
    # a small, sleeve-diverse sample -- not the full 94, but enough to prove
    # the pipeline composes end-to-end across genuinely different sleeves,
    # including the new multi-symbol ones (cross-sectional, stat-arb).
    wanted_ids = {
        "macd_trend_0", "zscore_reversion_0", "vol_breakout_0",
        "xsec_momentum", "stat_arb_distance_0", "trend_ma_cross_5_20",
        "carry_basis_0",
    }
    sample = [e for e in catalog.all() if e.manifest.id in wanted_ids]
    assert len(sample) == len(wanted_ids)  # every id must actually resolve

    returns_by_model: dict[str, list[float]] = {}
    sleeve_by_model: dict[str, str] = {}
    for entry in sample:
        strategy = entry.strategy_factory()
        session = run_backtest(
            run_id=f"divscore-test:{entry.manifest.id}", symbol=SYMBOL, bars=bars,
            strategy=strategy, starting_cash=Decimal("10000"),
        )
        returns = _bar_returns(session.equity_curve)
        if float(np.std(returns)) == 0.0:
            continue  # never traded this window -- correlation undefined, honestly excluded
        returns_by_model[entry.manifest.id] = returns
        sleeve_by_model[entry.manifest.id] = entry.manifest.sleeve

    assert len(returns_by_model) >= 2

    score = diversification_score(returns_by_model, sleeve_by_model)
    assert score.n_models == len(returns_by_model)
    assert -1.0 <= score.average_pairwise_correlation <= 1.0
    assert 1.0 <= score.effective_number_of_bets <= score.n_models
    assert score.n_sleeves >= 2
    assert 0.0 < score.max_sleeve_share <= 1.0

    # docs/14 M24 exit gate: the same real pipeline must also support
    # measuring carry_basis's correlation to the directional sleeves --
    # only assert this if the sustained perp premium actually triggered a
    # real (non-degenerate) carry_basis trade in this window.
    if "carry_basis" in sleeve_by_model.values():
        directional = {"trend_momentum", "mean_reversion", "volatility", "cross_sectional"}
        directional_present = directional & set(sleeve_by_model.values())
        cross_corr = cross_group_average_correlation(
            returns_by_model, sleeve_by_model, {"carry_basis"}, directional_present,
        )
        assert -1.0 <= cross_corr <= 1.0


def test_write_artifact_produces_the_exact_json_the_desk_panel_reads(tmp_path: Path) -> None:
    # docs/15 V5 M29: pins `_write_artifact`'s schema against
    # `ui/data.py::DeskData.diversification()`'s own parsing (int()/float()/
    # str() on these exact keys) without re-running the full catalog sweep.
    score = DiversificationScore(
        n_models=42, average_pairwise_correlation=0.257, effective_number_of_bets=6.5,
        n_sleeves=9, dominant_sleeve="trend_momentum", max_sleeve_share=0.31,
    )
    path = tmp_path / "diversification_score.json"
    _write_artifact(score, path)

    raw = json.loads(path.read_text())
    assert raw["n_models"] == 42
    assert raw["average_pairwise_correlation"] == pytest.approx(0.257)
    assert raw["effective_number_of_bets"] == pytest.approx(6.5)
    assert raw["n_sleeves"] == 9
    assert raw["dominant_sleeve"] == "trend_momentum"
    assert raw["max_sleeve_share"] == pytest.approx(0.31)
    # a real, parseable ISO timestamp -- not a placeholder string
    datetime.fromisoformat(raw["computed_at"])
    assert isinstance(raw["universe"], list) and len(raw["universe"]) > 0

    # the exact round-trip ui/data.py's DeskData.diversification() does
    assert int(raw["n_models"]) == 42
    assert float(raw["average_pairwise_correlation"]) == pytest.approx(0.257)
    assert str(raw["dominant_sleeve"]) == "trend_momentum"
