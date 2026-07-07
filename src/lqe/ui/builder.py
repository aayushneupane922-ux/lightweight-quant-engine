"""Assembles a `DeskData` from the real project pieces (audit log, model
catalog, experiment registry) so the CLI's `desk` command — and the tests —
have one place that wires them together.

This module deliberately lives in `ui/` but is the *composition seam*: it is
allowed to import `models` (for catalog rows) because it is invoked by the
CLI (cli → models via backtest), not by the rendering layer. The actual
render path (`ui/app.py`, `ui/data.py`) still imports only
`storage.state_reader` and `live.control`. Keeping the model-catalog import
here, not in `app.py`, is what preserves that boundary.

The `ControlPlane` (which owns the persistent kill switch) is built by the
caller and passed in — `ui/` never imports `risk` internals itself
(docs/11 §11.1); the CLI, which may import `risk`, constructs it.
"""

from __future__ import annotations

from pathlib import Path

from lqe.live.control import ControlPlane
from lqe.models.registry import build_default_catalog
from lqe.storage.state_reader import CatalogModelInfo, StateReader
from lqe.ui.data import CatalogRow, DeskData, ExperimentRow


def build_desk_data(
    *,
    control: ControlPlane,
    audit_path: Path | None = None,
    symbol: str = "BTC-USDT",
    experiment_rows: list[ExperimentRow] | None = None,
    diversification_path: Path | None = None,
) -> DeskData:
    catalog, results = build_default_catalog(symbol)
    quarantined = {q.model_id: q.reasons for q in catalog.quarantined()}

    catalog_rows = [
        CatalogRow(
            model_id=entry.manifest.id,
            family=entry.manifest.family,
            sleeve=entry.manifest.sleeve,
            one_liner=entry.manifest.one_liner,
            oss_libs=list(entry.manifest.oss_libs),
            status=entry.manifest.status,
        )
        for entry in catalog.all()
    ]
    catalog_rows += [
        CatalogRow(
            model_id=model_id,
            family="—",
            one_liner="",
            oss_libs=[],
            status="unproven",
            quarantined=True,
            quarantine_reason="; ".join(reasons),
        )
        for model_id, reasons in quarantined.items()
    ]

    catalog_info = [
        CatalogModelInfo(
            model_id=r.model_id, family=r.family, sleeve=r.sleeve, status="unproven",
            symbol=symbol,
        )
        for r in catalog_rows
        if not r.quarantined
    ]

    if audit_path is not None and audit_path.exists():
        state_reader = StateReader.from_jsonl(audit_path, catalog=catalog_info)
    else:
        state_reader = StateReader([], catalog=catalog_info)

    return DeskData(
        state_reader=state_reader,
        control=control,
        catalog_rows=catalog_rows,
        experiment_rows=experiment_rows or [],
        diversification_path=diversification_path,
    )
