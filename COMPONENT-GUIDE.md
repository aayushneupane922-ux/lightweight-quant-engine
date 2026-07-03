# Component Guide — how `lightweight-quant-engine` actually works

This is the deep-dive companion to [USER-GUIDE.md](USER-GUIDE.md) (which is a
command quickstart). USER-GUIDE tells you *what to type*; this tells you *what
happens when you do*, so you can operate, debug, and extend the product
yourself. Every claim below was verified against the running code on
2026-07-03, not recalled from memory — where the two disagree, trust this file
less than `grep`.

---

## 1. The mental model, in one paragraph

Everything the engine does is an **event**, appended to a **hash-chained audit
log**. A backtest replays historical bars through a **Strategy** → a
**RiskModel** gate → the **PaperBroker** → **Accounting**, one event at a time.
The **autonomy loop** (`lqe autopilot`) runs that same backtest machinery
*inside itself*, over and over, proposing parameter ranges, searching them
with Optuna, and judging each candidate with the same out-of-sample
**PromotionGate** a human would use via `lqe validate`. The **Obsidian Desk**
UI is a read-only window onto that audit log — it never drives the engine, it
only *replays* it and offers one narrow write path (`ControlPlane`) for
KILL/FREEZE/AUTOPILOT toggles. Nothing anywhere places a real order; the
`PaperBroker` is structurally the only thing that can ever fill an intent.

```
 ingest → curated Parquet → replay bundle (checksummed, frozen)
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
              lqe backtest                   lqe autopilot
        (one strategy, one pass)     (OBSERVE→HYPOTHESIZE→SEARCH→
                    │                 VALIDATE→DECIDE→NARRATE, looped)
                    │                              │
                    └──────────────┬───────────────┘
                                   ▼
                     hash-chained AuditLog (JSONL)
                                   │
                                   ▼
                    StateReader (read-only replay)
                                   │
                                   ▼
                     Obsidian Desk (FastAPI, 127.0.0.1)
                     Floor·Catalog·Research·Intel·Engine·Risk·Daily
```

---

## 2. The CLI — every command, what it touches, when to use it

Run any of these with `-h` for full flags. All read/write only inside the
`--root` directory you give them (default `data` or `runs` depending on
command) — nothing reaches outside your machine except `ingest --adapter ccxt`
(public market data, no key).

| Command | What it does | Reads | Writes |
|---|---|---|---|
| `lqe ingest` | Fetch (ccxt, public-only) or replay (CSV) OHLCV bars, run §8.4 data-quality checks (gaps, OHLC sanity, dupes, outliers), write curated Parquet + a DuckDB catalog entry. | exchange or CSV | `<root>/curated/`, `<root>/<catalog>.duckdb` |
| `lqe backtest` | One deterministic pass of one strategy over a **replay bundle** (a frozen, checksummed slice of curated data). Prints final paper equity + confirms the audit hash-chain verifies. | a replay bundle | nothing persisted unless you redirect stdout |
| `lqe validate` | The real product: walk-forward OOS split + Deflated Sharpe + PBO + a cost-bps sweep + random/equal-weight benchmarks, then the `PromotionGate` verdict. Writes a tearsheet and (if `--catalog` given) an `ExperimentRegistry` row. | a replay bundle | optional tearsheet file, optional catalog row |
| `lqe catalog` | Lists the **scaled** model catalog (51 registered) for a symbol: which are admitted (constructible now) vs transparently quarantined (missing optional lib), broken down by family. | nothing (pure listing) | nothing |
| `lqe check-config` | Validates a `.json`/`.toml` config against the paper-only lockout schema; a `mode: live` config is refused *by name*, not by generic schema failure. | a config file | nothing |
| `lqe autopilot` | Runs the autonomy loop N steps over a bundle: proposes a model + param range, runs Optuna trials, validates the best candidate, promotes on PASS, narrates. Deterministic given the same `--seed`. | a replay bundle | optional audit JSONL (`--out`), optional catalog trial-provenance (`--catalog`) |
| `lqe desk` | Serves the Obsidian Desk on `127.0.0.1`. Read-only render of an (optional) audit log + an (optional) kill-switch file. | an audit JSONL (optional), a kill-switch file (optional) | the kill-switch file, if you use the UI's KILL control |
| `lqe doctor` | Read-only health check: paper-only lockout, config-rejects-live, audit hash-chain (if given a log), kill-switch state, catalog build, license gate. `FAIL`→exit 1, `WARN`→exit 0. | whatever paths you point it at | nothing |
| `lqe backup` | Zips `data/`, `runs/`, `catalog.duckdb` into a timestamped archive. Skips whatever doesn't exist yet. | `data/`, `runs/`, `catalog.duckdb` | a zip under `backups/` |

`python run.py` is a thin wrapper around `lqe desk` that also opens your
browser (and optionally a native `pywebview` window with `--window`). Both
bind `127.0.0.1` only — there is no authentication because the app is
never reachable off loopback.

---

## 3. The Obsidian Desk — what each view actually shows

All seven views render from the **same** `StateReader`, which reconstructs
everything by replaying the audit log you pointed `lqe desk`/`run.py` at. If
you don't pass `--audit`, every view is honestly empty rather than faked.

| View | Key | Shows | Backed by |
|---|---|---|---|
| **Floor** | F1 | The "model floor" grid — one card per model in the **default catalog** (11 models: `trend_ma_cross`, `trend_macd_cross`, `donchian_breakout`, `trend_adx_filter`, `momentum_tsmom`, `momentum_roc`, `meanrev_zscore`, `meanrev_bollinger`, `meanrev_rsi`, `vol_breakout`, `naive_always_long`), each labeled `ARMED`/`unproven` with a live-fill sample size. | `models.registry.build_default_catalog` + replayed `SignalEvent`/`FillEvent`s |
| **Catalog** | F2 | The full model library with one-liners, licenses (`own`/library name), and status. Same 11-model default catalog (**not** the 51-model scaled one — see §5 nuance below). | `build_default_catalog` |
| **Research** | F3 | Gate evidence: Sharpe/DSR/PBO/max-DD/trades/cost-bps/verdict per experiment. Empty until you wire an `ExperimentRegistry` in (see §8 nuance). | `ExperimentRow` list passed into `build_desk_data` |
| **Intel** | F4 | Decision cards: one per autopilot step — `HYPOTHESIS → SEARCH (n trials) → VALIDATE: PASS/FAIL` with the gate's actual failure reasons spelled out, plus the autopilot ON/OFF toggle and "take the wheel" note. | replayed `HypothesisEvent`/`TrialEvent`/`ValidationEvent`/`NarrationEvent` |
| **Engine** | F7 | The 3D-style neural-web: a dependency-free `<canvas>` force-graph — `Market_Feed` node wired to every model node plus a purple `Meta-layer` node, colored by conviction/state, with an Inspector legend and a **timeline-replay scrubber** (`seq N/total`, deterministic). | `StateReader.graph(at_seq)` via `/api/graph` |
| **Risk** | F5 | Kill-switch state (`ACTIVE` green = trading permitted / kill not engaged, `KILLED` red = halted) and any active risk breaches. | `ControlPlane`/`KillSwitch` |
| **Daily** | F6 | Per-session paper P/L, trades, max intraday drawdown, and whether an independent reconciliation matched the running ledger. Empty until a session-close reconciliation record exists. | replayed reconciliation records |

**The one write path**: every mutating action in the UI (KILL, FREEZE,
AUTOPILOT ON/OFF, CLEAR_KILL) goes through `POST /api/control`, which is the
*only* thing that can touch `ControlPlane`. There is no other route that
writes anything — confirmed by `tests/safety/test_ui_boundary.py` (`UI
constructs no order`) and the module-layering test (`ui` imports only
`storage.state_reader` + `live.control` + `core`).

---

## 4. The safety spine (why nothing here can misbehave)

Four independent mechanisms, each enforced structurally (by AST/type checks
and tests), not by convention:

1. **Paper-only lockout.** `PaperBroker.is_paper = True` is the only
   `ExecutionAdapter`; `assert_paper_only` runs at every `Session` startup;
   the config schema's `mode` field is a closed `Literal["backtest","paper"]`
   — `mode: live` cannot even be expressed, let alone loaded
   (`core/config.py::_reject_live`). `LIVE_TRADING_ENABLED = False` in
   `constants.py` is never read conditionally anywhere.

2. **The risk gate.** Every `OrderIntent` passes through `RiskModel.check`
   before `make_order` (the *sole* `Order` constructor) is even callable.
   Twelve rules, fail-closed (missing/bad state → REJECT, never APPROVE by
   default): `kill_switch_active`, `max_drawdown`, `max_daily_loss`,
   `symbol_whitelist`, `stale_data`, `duplicate_signal`, `sane_qty`,
   `sane_price`, `max_orders_per_day`, `max_orders_per_min`,
   `max_pos_symbol` (CLAMPs), `max_gross_exposure` (CLAMPs),
   `cash_sufficiency`. A REJECT halts the whole intent; a CLAMP shrinks it.

3. **The kill switch** (`risk/kill_switch.py`). Disk-persisted, so it
   survives a restart; `trigger()` sets it, `clear(operator=...)` is the
   *only* way to reset it and raises `ValueError` on a falsy operator at the
   `KillSwitch` level. **Nuance worth knowing:** the web endpoint
   `POST /api/control` substitutes the literal string `"desk-operator"` if
   you post a blank operator field (`ui/app.py:134`), rather than rejecting
   the HTTP request — so a human at the browser can't accidentally get a
   raw 500, but the audit trail is left generically attributed rather than
   truly named. This is a deliberate UX choice (verified live — see §7), not
   a bypass: the important guarantee is that **no LLM/autonomy tool can ever
   reach this endpoint at all** — `autonomy/tools.py`'s five-tool whitelist
   has no kill/clear/order tool, so the loop cannot self-clear no matter
   what it "decides."

4. **The promotion gate** (`autonomy/promotion_gate.py`). The *only* place
   `GateResult` is constructed. A candidate PASSes only if it beats **all**
   of: `min_dsr=0.95` (Deflated Sharpe), `max_pbo=0.5` (Probability of
   Backtest Overfitting), `min_trades=30`, `min_periods=10_000`, plus (in
   `Validator`) survives a cost-bps sweep and beats random-entry/equal-weight
   controls. `TrackedBook.promote` re-checks the PASS before admitting a
   model — a stale or forged verdict can't slip through.

Every event of every kind (trading *and* autonomy: `HypothesisEvent`,
`TrialEvent`, `ValidationEvent`, `PromotionEvent`, `DeRiskEvent`,
`NarrationEvent`, `LlmCallEvent`, `ControlEvent`, ...) is hash-chained in the
same `AuditLog`. `AuditLog.verify()` walks the chain; `AuditLog.from_jsonl`
re-verifies on load and raises on a tampered/truncated file rather than
loading it. `lqe doctor --audit <path>` runs this check for you.

---

## 5. The autonomy loop, step by step

One `Orchestrator.step()` = one full turn:

```
OBSERVE     — read the current book state (sandbox vs tracked)
HYPOTHESIZE — pick a model + a parameter range to explore
              (rule-based by default; an optional local LLM narrator
               may propose ranges too — see below)
SEARCH      — OptunaOptimizer runs N seeded trials inside that range
VALIDATE    — the SAME Validator/PromotionGate a human uses via
              `lqe validate` judges the best trial out-of-sample
DECIDE      — PASS → TrackedBook.promote (re-checks the verdict)
              FAIL → nothing promoted, reasons recorded
NARRATE     — a plain-language summary of what happened, written
              by the RuleBasedNarrator (default) or an optional local
              Ollama model (`--llm`, graceful fallback if the server
              is absent — no network dependency either way)
```

**The LLM's entire vocabulary is five tool calls** (`autonomy/tools.py`):
`propose_space` (suggest ranges), `run_trials` (ask for N more),
`promote_if_valid` (ask the gate to check — cannot force a PASS),
`de_risk` (REDUCE/PAUSE/RETIRE a tracked model on drift), `narrate` (explain).
There is no sixth tool, and the parser is **fail-closed**: a malformed or
hallucinated tool call (e.g. a fictional `place_order`) is dropped, never
executed. The LLM never touches the numeric search (Optuna does that) and
never overrides the gate (only the `Validator` sets `validated`).

`DriftMonitor` watches the tracked book's live performance and can trigger a
`DeRiskEvent` (REDUCE/PAUSE/RETIRE) on degradation — it never "chases" a
winning streak, only backs off a losing one.

**Trial-counting honesty:** pass `--catalog <db>` to `lqe autopilot` and every
trial across every campaign is persisted to an `ExperimentRegistry`, so the
DSR/PBO deflation math sees the *honest* total trial count, not just this
run's. Re-running the identical campaign (same bundle+symbol+seed+steps)
*replaces* its own trials rather than double-counting; a genuinely different
campaign accumulates.

---

## 6. The model catalog — two catalogs, on purpose

This is the single most likely point of confusion, so it gets its own
section:

- **`models.registry.build_default_catalog`** — 11 hand-picked models across
  4 families (trend/momentum/mean_reversion/volatility), used by the
  **Obsidian Desk** (Floor/Catalog views) and by `default_searchable_models()`
  which feeds **exactly 3** of them (`trend_ma_cross`, `momentum_tsmom`,
  `meanrev_rsi`) into the autopilot's *searchable* surface. This is the
  intentionally small M8 proving surface.
- **`models.catalog_scale.build_scaled_catalog`** — 51 models reached by
  "**config, not per-model files**": presets × parameter grids over the same
  native indicator engine, plus adapters for 8 heavier libraries (pairs
  trading, HMM regime detection, change-point detection, supervised/LightGBM
  signals, GARCH volatility, 3 portfolio optimizers). This is what
  **`lqe catalog`** lists and what `lqe doctor`'s catalog check builds.

Every model — in either catalog — is `unproven` until an actual `lqe
validate` (or an autopilot step) gives it a gate PASS. Breadth never confers
validation; only the gate does (`test_every_admitted_model_is_unproven_until_gated`).

**Optional heavy libraries and quarantine:** `pip install .[models]` (or the
individual packages) unlocks the heavy adapters; without them, `intake_check`
quarantines each one *transparently* with a clear reason
(`"... requires the optional 'models' extra: pip install '.[models]'"`) —
never a crash, never a silent drop. On this machine, `statsmodels`/`arch`/
`hmmlearn`/`ruptures`/`scikit-learn`/`lightgbm` are installed (catalog admits
48/51); the 3 cvxpy-based portfolio optimizers (PyPortfolioOpt/skfolio/
riskfolio-lib) remain quarantined because their `jupyter-widgets`/`vectorbt`
dependency chain trips Windows' 260-character path limit unless
`LongPathsEnabled=1` is set (admin + reboot) — see USER-GUIDE §1 for the fix.

---

## 7. What I verified live, right now (not just read in the code)

- `lqe doctor` → all core checks OK; license gate PASS (50 runtime deps).
- `lqe ingest` (CSV) → 600 bars curated, checksummed, versioned.
- `lqe backtest` → paper equity computed, **audit hash-chain verifies: True**.
- `lqe autopilot --steps 4` → a real 4-step campaign (all FAIL — the honest
  outcome on synthetic data with no real edge), audit hash-chain verifies,
  wrote a real JSONL the desk replays.
- The desk, served on `127.0.0.1:8137`, rendered all 7 views from that log
  with no console errors.
- **`POST /api/control {"command":"KILL","operator":"demo-operator"}`** →
  `kill_active: true`; the Risk view flipped to red `KILLED`; the header
  pill flipped from `PAPER · LIVE LOCKED` to `KILLED`.
- **`POST /api/control {"command":"CLEAR_KILL","operator":"demo-operator"}`**
  → `kill_active: false`, confirming the clear path works end-to-end.
- **`POST /api/control {"command":"PLACE_ORDER","operator":"x"}`** → HTTP
  **400** — confirming there is no order-placing command in the whitelist,
  live, not just in the source.
- **`POST /api/control {"command":"CLEAR_KILL","operator":""}`** (kill
  genuinely active at the time) → returned `kill_active: false`, HTTP 200 —
  this is the operator-fallback nuance from §4.3, confirmed live rather than
  assumed from the docstring.

---

## 8. Known nuances (accurate as of this session — not bugs, but worth knowing)

- **Research view (F3) needs manual wiring.** `lqe desk`/`run.py` don't
  currently accept a `--catalog` flag to load persisted `ExperimentRegistry`
  rows into the Research view — `build_desk_data(experiment_rows=...)`
  supports it, but the CLI doesn't plumb it through yet. Today, Research
  populates only if you call `build_desk_data` yourself with rows loaded from
  a catalog. Easy follow-up if you want it.
- **The autopilot's searchable surface (3 models) is much smaller than the
  full catalog (51 models).** This is intentional per the roadmap (M8 proves
  the loop; M11 scales the *catalog*, not yet the *searchable set*) — but if
  you expected autopilot to explore all 51, it currently only explores those
  3 by default (`autonomy/searchable.default_searchable_models`).
- **The kill-clear operator fallback** (§4.3/§7): the web API defaults a
  blank operator to `"desk-operator"` rather than hard-rejecting, unlike the
  `KillSwitch.clear()` primitive it calls, which does hard-raise on a falsy
  operator when called directly (e.g. from the CLI or tests).
- **Windows long-path limit** blocks the full `.[models]` install (§6). The
  jupyter-free statistical subset installs cleanly and is what's on this
  machine now.

None of these weaken a lockout, the gate, or the audit chain — they're UX/
scope gaps, not safety gaps.

---

## 9. Where things live (file map)

```
src/lqe/
  core/        event types, clock, engine/audit log, config+lockout, make_order
  data/        ccxt (public data only) + CSV adapters, ingest pipeline, validation
  storage/     Parquet, DuckDB catalog, replay bundles, StateReader (read-only)
  portfolio/   Decimal accounting, position sizing, multi-instrument reconciliation
  execution/   PaperBroker (the only ExecutionAdapter), fills/slippage/commission
  risk/        the 12-rule gate, kill switch, reconciliation/rebuild-from-audit
  analytics/   metrics, DSR, PBO, ExperimentRegistry, tearsheet
  autonomy/    optimizer (Optuna), drift monitor, orchestrator, tools, narrator,
               promotion_gate, validator, books (sandbox/tracked), searchable
  models/      manifest schema, catalog + intake/quarantine, catalog_scale (51),
               plugins/ (native strategies), adapters/ (heavy-lib + indicators)
  backtest/    one-shot runner wiring a ReplayClock + Session
  live/        ControlPlane — the UI's one write path
  ui/          FastAPI app, Jinja2 templates, builder.py (composition seam)
  viz3d/       the dependency-free canvas force-graph JS
  ops/         lqe doctor + lqe backup
  cli.py       argparse wiring for every `lqe <command>`
run.py         one-command local launcher (wraps `lqe desk`)
scripts/       license_gate.py, generate_third_party_notices.py, make_demo_run.py
docs/          the full spec (00-11) + docs/archive (superseded, reference only)
tests/         unit/ property/ parity/ safety/ honesty/ integration/
```

---

## 10. Recipes

**"I want to see it live again with a fresh demo run":**
```
python scripts/make_demo_run.py
lqe backtest --root data --bundle demo --symbol BTC-USDT --fast 8 --slow 32
lqe autopilot --root data --bundle demo --symbol BTC-USDT --steps 4 --trials 8 --seed 7 --min-periods 200 --out runs/demo-audit.jsonl
python run.py --audit runs/demo-audit.jsonl --kill-switch runs/demo-kill.json
```

**"I want to run it on real crypto data":**
```
lqe ingest --adapter ccxt --exchange binance --symbol BTC-USDT --timeframe 1m
# then build a bundle (see storage/replay_bundle.build_bundle, or extend the CLI)
```

**"I want to check nothing is broken before I trust a run":**
```
lqe doctor --audit <path> --kill-switch <path>
```

**"I want to add a new model":** write a `models/plugins/<name>.py` with a
`MANIFEST = ModelManifest(...)` + `make_strategy(symbol)`, add it to
`models/registry.build_default_catalog`. See any existing plugin for the
pattern — each is ~40 lines.

**"I want the gate to judge my own strategy":**
```
lqe validate --bundle <bundle-id> --symbol BTC-USDT --strategy trend_ma_cross --tearsheet-out sheet.txt
```
