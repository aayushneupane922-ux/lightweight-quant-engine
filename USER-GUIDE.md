# User Guide — `lightweight-quant-engine` v1.0

A local, **paper-only** autonomous quant-research simulator. It runs on your
machine, serves a browser UI on `localhost`, costs ~$0/month, and **cannot
place a real trade or claim a profit**. This guide is how to *run* the finished
app; the specs live in `docs/`, and the build history in `HANDOFF.md`.

> Everything here is simulated. A "tracked" equity curve is a gate-passed,
> out-of-sample, after-cost *paper* result — not evidence of a real edge.

## 1. Install

```
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -e ".[ui,search,dev]"     # the running product + dev tools
```

Extras are opt-in and layered:
- **base** — engine, data, backtest, gate, risk, CLI (no extra needed).
- **`ui`** — the Obsidian Desk web UI (FastAPI + Jinja2).
- **`search`** — Optuna, for the autonomy loop (`lqe autopilot`).
- **`data`** — Polars/pandas, for heavier data transforms.
- **`models`** — the heavy structural adapters (statsmodels/arch/hmmlearn/
  ruptures/skfolio/…). *Optional by design*: without it those catalog models
  quarantine transparently rather than crash.

## 2. Health check first

```
lqe doctor
```

Read-only. Verifies the paper-only lockout, that a live config is refused, the
catalog builds, and the license gate passes. Point it at a run to check more:

```
lqe doctor --audit runs/audit.jsonl --kill-switch runs/kill.json
```

`FAIL` (a broken invariant) exits non-zero; `WARN` (e.g. no audit log supplied,
or an *active* kill switch) is informational and exits 0.

## 3. The core workflow

### Ingest market data (public crypto, no API key)
```
lqe ingest --adapter ccxt --exchange binance --symbol BTC-USDT --timeframe 1m
```
Or replay a CSV you already have:
```
lqe ingest --adapter csv --exchange local --symbol BTC-USDT --timeframe 1m --csv-path bars.csv
```
Data lands in `data/` as partitioned Parquet, indexed by a DuckDB catalog, and
is frozen into a checksummed **replay bundle** for reproducibility.

### Backtest a strategy (deterministic)
```
lqe backtest --bundle <bundle-id> --symbol BTC-USDT --fast 12 --slow 48
```
Prints final paper equity and confirms the audit hash-chain verifies.

### Run the promotion gate — the real product
```
lqe validate --bundle <bundle-id> --symbol BTC-USDT --tearsheet-out sheet.txt
```
Walk-forward + Deflated Sharpe + PBO + a cost sweep + random/equal-weight
benchmarks. Nothing becomes `validated` without a **PASS** here.

### List the model catalog
```
lqe catalog
```
51 models across 4 families; each is `unproven` until a gate PASS promotes it.
Models needing the `models` extra show up transparently quarantined.

## 4. The autonomy loop (autopilot)

```
lqe autopilot --bundle <bundle-id> --symbol BTC-USDT --steps 3 --trials 12 --seed 0
```
A deterministic OBSERVE → HYPOTHESIZE → SEARCH → VALIDATE → DECIDE → NARRATE
loop: Optuna searches, the Validator judges, and only gate-PASS candidates reach
the tracked book. Add `--catalog catalog.duckdb` to persist honest cross-campaign
trial counts. Add `--llm` to narrate via a local Ollama server (falls back to the
rule-based narrator if it's absent — no network dependency).

## 5. The Obsidian Desk UI

```
python run.py                 # serve + open a browser tab
python run.py --window        # native desktop window (needs `pip install pywebview`)
python run.py --audit runs/audit.jsonl --kill-switch runs/kill.json
```
Or the equivalent CLI form: `lqe desk --audit runs/audit.jsonl`.

**Both bind `127.0.0.1` only.** There is no authentication because the app is
never reachable off the loopback interface. Views: Floor, Catalog, Research,
Intel (decision cards + take-the-wheel), Engine (3D neural-web), Risk, Daily.

The **KILL** button (Risk view) flips a disk-persisted, human-owned kill switch
that the risk gate reads; it blocks every risk-increasing order, survives a
restart, never auto-clears, and can only be cleared by a **named operator**. The
LLM/autonomy can never place an order or clear the kill switch.

## 6. Backups

```
lqe backup                    # zip data/, runs/, catalog.duckdb -> ./backups/
lqe backup --root . --dest D:/lqe-backups
```
Read-only w.r.t. the sources; missing sources are skipped, not an error.

## 7. Verify the whole thing

```
pytest -q                             # full suite
ruff check .                          # lint
mypy src                              # types (strict)
python scripts/license_gate.py        # runtime-dependency license gate
```
The release safety/honesty review with evidence is in `M12-RELEASE-REVIEW.md`.

## 8. What it will never do
No real orders, no broker SDK, no credentials. It refuses a `mode: live` config
by name. It makes no profitability claim. If you want to understand *why* each of
those is structurally impossible rather than merely disabled, read `GUARDRAILS.md`
and `M12-RELEASE-REVIEW.md`.
