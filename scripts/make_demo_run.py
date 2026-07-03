"""Generate a small demo dataset + replay bundle so the desk has real content
to render (a local convenience script, not part of the shipped product).

    python scripts/make_demo_run.py

Produces:
  data/                      curated OHLCV + DuckDB catalog
  data/replay/demo/          a frozen, checksummed replay bundle "demo"
Then run:  lqe autopilot --root data --bundle demo --out runs/demo-audit.jsonl ...
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

from lqe.data.csv_replay import CsvReplayAdapter
from lqe.data.ingest import ingest
from lqe.storage.catalog import Catalog
from lqe.storage.replay_bundle import build_bundle

N_BARS = 600
SYMBOL = "BTC-USDT"
EXCHANGE = "demo"
TIMEFRAME = "1m"


def _bars_csv() -> str:
    """A gently trending, mean-reverting price path (smooth enough to pass the
    §8.4 data-quality checks: no gaps, OHLC-sane, no synthetic outliers)."""
    rows = ["ts_open,open,high,low,close,volume"]
    price = 100.0
    for i in range(N_BARS):
        h, m = divmod(i, 60)
        ts = f"2026-01-01T{h:02d}:{m:02d}:00+00:00"
        # trend + slow cycle, tiny deterministic wiggle — no big jumps
        drift = 0.03 * i
        cycle = 6.0 * math.sin(i / 40.0)
        wiggle = 0.4 * math.sin(i / 3.0)
        close = 100.0 + drift + cycle + wiggle
        openp = price
        high = max(openp, close) + 0.5
        low = min(openp, close) - 0.5
        rows.append(f"{ts},{openp:.2f},{high:.2f},{low:.2f},{close:.2f},{10 + (i % 5)}")
        price = close
    return "\n".join(rows) + "\n"


def main() -> int:
    root = Path("data")
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / "demo_bars.csv"
    csv_path.write_text(_bars_csv(), encoding="utf-8")

    adapter = CsvReplayAdapter(csv_path, exchange=EXCHANGE, symbol=SYMBOL, timeframe=TIMEFRAME)
    with Catalog(root / "catalog.duckdb") as catalog:
        result = ingest(
            adapter, exchange=EXCHANGE, symbol=SYMBOL, timeframe=TIMEFRAME,
            root=root, catalog=catalog,
        )
    print(f"ingested {result.rows} bars -> version {result.version_id}")

    bundle = build_bundle(
        root,
        bundle_id="demo",
        exchange=EXCHANGE,
        symbols=[SYMBOL],
        timeframe=TIMEFRAME,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        seed=7,
        source_versions=[result.version_id],
    )
    print(
        f"built replay bundle {bundle.bundle_id!r} "
        f"({len(bundle.symbols)} symbol, seed {bundle.seed})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
