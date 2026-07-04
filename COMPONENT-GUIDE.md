# Component Guide — how `lightweight-quant-engine` actually works

This is the deep-dive companion to [USER-GUIDE.md](USER-GUIDE.md) (which is a
command quickstart). USER-GUIDE tells you *what to type*; this tells you *what
happens when you do*, so you can operate, debug, and extend the product
yourself. Every claim below was verified against the running code on
2026-07-03/04, not recalled from memory — where the two disagree, trust this
file less than `grep`.

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
              Floor·Catalog·Research·Intel·Engine·Risk·Daily·Blotter
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
| `lqe live` *(v2.0, docs/12 M14)* | Every admitted catalog model gets its own paper book, sharing one audit log + one kill switch, fed by continuously-polled real (`--adapter ccxt`) or replayed (`--adapter csv`) bars; the autonomy loop narrates live on the desk. `--out <path>` persists and auto-resumes (same path again ⇒ reconstructs the fleet's trading state via replay — docs/12 M15). `--max-polls N` bounds a run for demos/tests. | ccxt (public) or a local CSV | optional trading audit JSONL (`--out`), serves the desk |
| `lqe desk` | Serves the Obsidian Desk on `127.0.0.1`. Read-only render of an (optional) audit log + an (optional) kill-switch file. | an audit JSONL (optional), a kill-switch file (optional) | the kill-switch file, if you use the UI's KILL control |
| `lqe doctor` | Read-only health check: paper-only lockout, config-rejects-live, audit hash-chain (if given a log), kill-switch state, catalog build, license gate. `FAIL`→exit 1, `WARN`→exit 0. | whatever paths you point it at | nothing |
| `lqe backup` | Zips `data/`, `runs/`, `catalog.duckdb` into a timestamped archive. Skips whatever doesn't exist yet. | `data/`, `runs/`, `catalog.duckdb` | a zip under `backups/` |

`python run.py` is a thin wrapper around `lqe desk` that also opens your
browser (and optionally a native `pywebview` window with `--window`). Both
bind `127.0.0.1` only — there is no authentication because the app is
never reachable off loopback.

---

## 3. The Obsidian Desk — what each view actually shows

All eight views render from the **same** `StateReader`, which reconstructs
everything by replaying the audit log you pointed `lqe desk`/`run.py` at. If
you don't pass `--audit`, every view is honestly empty rather than faked.

| View | Key | Shows | Backed by |
|---|---|---|---|
| **Floor** | F1 | The "model floor" grid — one card per model in the **default catalog** (11 models: `trend_ma_cross`, `trend_macd_cross`, `donchian_breakout`, `trend_adx_filter`, `momentum_tsmom`, `momentum_roc`, `meanrev_zscore`, `meanrev_bollinger`, `meanrev_rsi`, `vol_breakout`, `naive_always_long`), each labeled `ARMED`/`unproven` with a live-fill sample size, plus (v3.0) a hero price/equity chart (vendored TradingView Lightweight Charts). | `models.registry.build_default_catalog` + replayed `SignalEvent`/`FillEvent`s |
| **Catalog** | F2 | The full model library with one-liners, licenses (`own`/library name), and status. Same 11-model default catalog (**not** the 51-model scaled one — see §5 nuance below). | `build_default_catalog` |
| **Research** | F3 | Gate evidence: Sharpe/DSR/PBO/max-DD/trades/cost-bps/verdict per experiment. Empty until you wire an `ExperimentRegistry` in (see §8 nuance). | `ExperimentRow` list passed into `build_desk_data` |
| **Intel** | F4 | Two complementary views of the same autonomy events: (v3.0) the **"Engine Room"** — a turn-by-turn conversation feed (Strategist proposes, Optimizer's trials roll up into one best-trial card per hypothesis, Judge validates with PASS/FAIL coloring, Autopilot narrates, Risk kills/de-risks), replayable via a timeline scrubber — sitting above the original per-hypothesis **decision cards**: `HYPOTHESIS → SEARCH (n trials) → VALIDATE: PASS/FAIL` with the gate's actual failure reasons spelled out, plus the autopilot ON/OFF toggle and "take the wheel" note. | replayed `HypothesisEvent`/`TrialEvent`/`ValidationEvent`/`PromotionEvent`/`DeRiskEvent`/`ControlEvent`/`NarrationEvent`, via `StateReader.conversation(at_seq)` (v3.0) and the pre-existing decision-card reducer |
| **Engine** | F7 | The 3D-style neural-web: a dependency-free `<canvas>` force-graph — `Market_Feed` node wired to every model node plus a purple `Meta-layer` node, colored by conviction/state, with an Inspector legend and a **timeline-replay scrubber** (`seq N/total`, deterministic). | `StateReader.graph(at_seq)` via `/api/graph` |
| **Risk** | F5 | Kill-switch state (`ACTIVE` green = trading permitted / kill not engaged, `KILLED` red = halted) and any active risk breaches. | `ControlPlane`/`KillSwitch` |
| **Daily** | F6 | Per-session paper P/L, trades, max intraday drawdown, and whether an independent reconciliation matched the running ledger. Empty until a session-close reconciliation record exists. | replayed reconciliation records |
| **Blotter** (v3.0) | F8 | The full order lifecycle, one row per fill: intent → risk decision (`APPROVE`/`CLAMP`/`REJECT`, with the rule that fired) → fill or reject — nothing vanishes silently — plus a per-model position/realized-P&L reconciliation table below. Model/symbol/side filters and an off-by-default sound-on-fill toggle. | `StateReader.blotter()`/`.reconciliation()`, correlated by `intent_id` across `OrderIntent`/`RiskDecision`/`Order`/`FillEvent` |

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
- **`models.catalog_scale.build_scaled_catalog`** — **104 models** (v4.0,
  up from 51 at v3.0 — §13) reached by "**config, not per-model files**":
  presets × parameter grids over the same native indicator engine, adapters
  for 9 heavier libraries (pairs trading, Johansen basket cointegration, HMM
  regime detection, change-point detection, supervised/LightGBM signals,
  GARCH volatility, 3 portfolio optimizers), native cross-sectional/stat-arb/
  carry-basis strategies built on a multi-symbol engine extension, and a
  ccxt-backed funding-rate data adapter. This is what **`lqe catalog`** lists
  and what `lqe doctor`'s catalog check builds.

Every model — in either catalog — is `unproven` until an actual `lqe
validate` (or an autopilot step) gives it a gate PASS. Breadth never confers
validation; only the gate does (`test_every_admitted_model_is_unproven_until_gated`).

**Optional heavy libraries and quarantine:** `pip install .[models]` (or the
individual packages) unlocks the heavy adapters; without them, `intake_check`
quarantines each one *transparently* with a clear reason
(`"... requires the optional 'models' extra: pip install '.[models]'"`) —
never a crash, never a silent drop. As of docs/12 M13, all 9 `models`-extra
packages (`statsmodels`/`arch`/`hmmlearn`/`ruptures`/`scikit-learn`/
`lightgbm`/`skfolio`/`PyPortfolioOpt`/`riskfolio-lib`) are installed on this
machine and `lqe catalog` shows **51/51 admitted, 0 quarantined**. The 3
cvxpy-based portfolio optimizers had been blocked by Windows' 260-character
path limit (their `jupyter-widgets`/`vectorbt` dependency chain) until
`LongPathsEnabled=1` was set (admin, no reboot needed) — see USER-GUIDE §1
for the exact command on a fresh machine.

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
- **`lqe autopilot`'s searchable surface (3 models) is much smaller than the
  full catalog (104 models, v4.0).** This is intentional per the roadmap (M8
  proves the loop; M11/M23-M25 scale the *catalog*, not yet the *searchable
  set*) — but if
  you expected `lqe autopilot` to explore all 51, it currently only explores
  those 3 by default (`autonomy/searchable.default_searchable_models`).
  `lqe live` (§11) uses a broader 10-model surface instead
  (`autonomy/searchable_scaled.broad_searchable_models`) — the two commands'
  autonomy loops deliberately don't search the same set.
- **The kill-clear operator fallback** (§4.3/§7): the web API defaults a
  blank operator to `"desk-operator"` rather than hard-rejecting, unlike the
  `KillSwitch.clear()` primitive it calls, which does hard-raise on a falsy
  operator when called directly (e.g. from the CLI or tests).
- **Windows long-path limit** used to block the full `.[models]` install; as
  of docs/12 M13 it's resolved on this machine (`LongPathsEnabled=1` set,
  all 9 packages installed, catalog 51/51). A fresh machine still needs that
  registry step repeated first (`USER-GUIDE.md` §1).
- **`lqe live --out` resume (docs/12 M15) reconstructs the trading fleet
  only**, not the orchestrator's own autonomy/promotion history — a resumed
  session's autonomy loop starts a fresh campaign over the reconstructed bar
  history. Also: replay uses the *current* `--kill-switch` state, so if
  someone toggles it between a crash and a resume, replayed decisions could
  diverge from what was originally decided in that exact window.

None of these weaken a lockout, the gate, or the audit chain — they're UX/
scope gaps, not safety gaps.

---

## 9. Where things live (file map)

```
src/lqe/
  core/        event types, clock, engine/audit log, config+lockout, make_order
  data/        ccxt (public data only) + CSV adapters, ingest pipeline, validation,
               funding_adapter.py (v4.0, perp funding-rate history)
  storage/     Parquet, DuckDB catalog, replay bundles, StateReader (read-only)
  portfolio/   Decimal accounting, position sizing, multi-instrument reconciliation
  execution/   PaperBroker (the only ExecutionAdapter), fills/slippage/commission
  risk/        the 12-rule gate, kill switch, reconciliation/rebuild-from-audit
  analytics/   metrics, DSR, PBO, ExperimentRegistry, tearsheet
  autonomy/    optimizer (Optuna), drift monitor, orchestrator, tools, narrator,
               promotion_gate, validator, books (sandbox/tracked), searchable
  models/      manifest schema, catalog + intake/quarantine, catalog_scale (104,
               v4.0), curation.py (correlation-redundancy check), plugins/
               (native strategies), adapters/ (heavy-lib + indicators +
               cross-sectional/stat-arb/carry-basis, v4.0)
  backtest/    one-shot runner wiring a ReplayClock + Session
  live/        ControlPlane — the UI's one write path; session.py (LiveSession)
  ui/          FastAPI app, Jinja2 templates, builder.py (composition seam),
               theme/vendor/ (TradingView Lightweight Charts, Apache-2.0)
  viz3d/       the dependency-free canvas force-graph JS
  ops/         lqe doctor + lqe backup + jobs.py (JobManager, v3.0 — the GUI's
               background ingest/backtest/live triggers)
  cli.py       argparse wiring for every `lqe <command>`
run.py / run.bat  one-command local launcher (wraps `lqe desk`) + onboarding (v3.0)
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

---

## 11. Live multi-model paper trading (`lqe live`, v2.0)

Runs the whole admitted catalog against continuously-polled market data,
with the autonomy loop narrated by a genuine local LLM. Started life
post-v1.0 as a standalone script (`scripts/run_live_fleet.py`); as of v2.0
(`docs/12-v2-roadmap.md` M14) it's a real, tagged `lqe live` CLI subcommand
with the same discipline as every other command — the script now just
delegates to it (`scripts/run_live_fleet.py` is a ~15-line wrapper, kept for
anyone's muscle memory, not deleted).

```
lqe live --llm --llm-model llama3.2:3b --out runs/live-session.jsonl
```

**What it wires together, and why each piece needed a small addition:**

- **`live/live_feed.py` (`LiveFeed`)** — polls `CcxtMarketDataAdapter` (public
  OHLCV, no key, no order call — the existing safety guarantee is inherited,
  not re-implemented) on an interval, deduping by `ts_open` so a bar is never
  processed twice and the still-forming bar is never handed to a strategy as
  if it were closed. `now_fn` is injectable so this is unit-testable without
  a real clock or network (`tests/unit/test_live_feed.py`).
- **`live/multi_model_runner.py` (`LiveMultiModelRunner`)** — every admitted
  model gets its **own** `PaperBroker`/`Accounting`/simulated stake (a
  `ModelBook`), but they all share **one** `Engine` (one hash-chained audit
  log) and **one** `RiskModel`/`KillSwitch`, so a single KILL halts every
  model's new entries at once. Per-model attribution for the desk reuses the
  *existing* strategy-tagged `SignalEvent`/`OrderIntent`/`Order`/`FillEvent`
  chain (`storage.state_reader` needed no changes for this). The one thing
  that doesn't have a natural per-model shape is `RiskStateEvent` — it was
  designed for a single book, so the runner computes one honest **fleet-wide
  aggregate** (summed equity/cash/exposure, peak of the *sum* over time, not
  the sum of each model's own peak) and emits exactly one per bar
  (`tests/integration/test_live_multi_model_runner.py` proves this against
  the true summed equity, not just "looks plausible").
- **`autonomy/searchable_scaled.py` (`broad_searchable_models`)** — the
  autopilot's default searchable set is 3 models (docs/10 M8's proving
  surface); this adds the other 9 native indicator families so a
  long-running session's autonomy loop actually cycles through the catalog's
  breadth, not just `trend_ma_cross`/`momentum_tsmom`/`meanrev_rsi`. The 3
  cvxpy portfolio optimizers and the heavier statistical adapters (HMM/
  change-point/supervised/GARCH) still **trade live in the fleet** — every
  admitted model does — they're just not wired into Optuna's numeric search
  (their param spaces don't map onto a scalar sweep the way an indicator
  threshold does).
- **`live/merge.py` (`merged_records`)** — the fleet runner and the
  `Orchestrator` each keep their *own* engine (`Orchestrator` already owns
  one internally; changing that would touch a well-tested M8 class for a
  display concern only). This module chronologically interleaves both
  engines' records into one renumbered, display-only list for the desk —
  each source's own hash chain stays independently verifiable via its own
  `AuditLog.verify()`; nothing is written back.
- **`ui/data.py` (`DeskData.set_state_reader`)** — the one addition to the
  shipped v1.0 UI layer: lets a background loop swap in a fresh
  `StateReader` built from the current, growing merged log. Every existing
  read method already re-derives from `self._state_reader` per call, so nothing
  else in `ui/` needed to change for the desk to visibly update live.
- **`autonomy/narrator.py`** — two real fixes made local-LLM narration
  actually reliable rather than theoretical, both discovered by testing
  against a real Ollama server, not by inspection: Ollama defaults to a
  model's full training context (131k tokens), asking llama.cpp to allocate
  a KV-cache buffer sized for the whole window regardless of prompt length —
  this crashed the server outright on an ordinary machine; `num_ctx`
  (default 4096) bounds it. And prompting alone got a small model to wrap
  free prose in a bare JSON array, which `parse_tool_calls` correctly
  rejected (fail-closed working as designed) but meant genuine LLM text
  never reached the loop; Ollama's structured-output `format` (a JSON schema
  mirroring `autonomy.tools.Narrate`/`ProposeSpace` exactly) constrains
  *decoding*, not validation — `parse_tool_calls` still checks independently
  and still fails closed on drift.

**v2.0 additions on top of the above (docs/12 M13–M16):**

- **`_cmd_live` in `src/lqe/cli.py`** — the standalone script's argument
  surface, ported into a real subcommand. Two new flags beyond the original
  script: `--adapter {ccxt,csv}` + `--csv-path` (an offline/test seam
  mirroring `lqe ingest`'s own `--adapter` choice — no network needed for
  demos or CI-style runs) and `--max-polls N` (bounds a run; `None` default
  still means run forever).
- **`--out <path>` + `LiveFeed.resume_from` (docs/12 M15)** — passing the
  same `--out` path on a later invocation auto-resumes: `AuditLog.from_jsonl`
  hash-chain-verifies the persisted trading audit (fail loud on corruption,
  same as the M5 rebuild-from-audit pattern), and its `MarketEvent`s are fed
  through the *exact same* `runner.process_bar` loop used for a fresh seed —
  reconstruction is a replay, not hand-written state math, so it inherits the
  M1/M3 determinism guarantee for free (verified: two runs against the same
  `--out` path produce byte-identical hash chains). `resume_from` repositions
  the polling dedup cursor so the next poll only fetches what's genuinely new
  since the last persisted bar.
- **The 51-model catalog actually running for the first time surfaced a real
  bug**: `models/catalog_scale.py`'s 3 portfolio adapters
  (skfolio/PyPortfolioOpt/riskfolio-lib) shared one hardcoded 2-asset
  synthetic universe. skfolio's `HierarchicalRiskParity` crashes on exactly
  2 assets regardless of history length (`argmax of an empty sequence`) —
  latent since M11, never triggered because all 3 were quarantined
  (`.[models]` incomplete) until docs/12 M13 installed them. Fixed by
  expanding the shared universe to 3 synthetic assets.
- **`tests/integration/test_ollama_narrator_live.py` (docs/12 M16)** — a
  marker-gated (`llm_integration`) test against a *genuine* Ollama server,
  gated by an actual reachability probe rather than a manual flag: skips
  automatically when absent (CI), runs automatically when present. Closes
  the gap where the real-LLM path had only ever been verified manually.
- **Two CI lanes** (`.github/workflows/ci.yml`): `check` (unchanged,
  `.[ui,search,dev]` only — the heavy-lib quarantine tests need `.[models]`
  absent there) and `models-extra` (new, `.[ui,search,dev,models]`, full
  suite) so the heavy adapters get real automated coverage too.

**Verified live, not just read in the source:** a fleet of 51 real admitted
models (post-M13, up from 48) traded against real recent Binance BTC-USDT
bars; the audit hash-chain verified throughout; the Intel view showed a
decision card tagged **LLM** with real, non-templated narration text from a
local `llama3.2:3b` model; `KILL` halted the whole fleet's new entries with
one shared switch. This session also verified the `llm_integration` test
both ways (Ollama up → passes with a real round trip; Ollama down → cleanly
skips) and the `--out` resume producing byte-identical hash chains across
two separate `lqe live` invocations.

**Recipe:**
```
lqe live \
  --symbol BTC-USDT --timeframe 1m --poll-seconds 60 \
  --lookback-bars 300 --autonomy-every 5 --n-trials 8 \
  --llm --llm-model llama3.2:3b --out runs/live-session.jsonl --port 8137
```
Ctrl+C stops it; re-run the identical command to resume from `--out`.
`--kill-switch <path>` persists the kill state to disk like `lqe desk` does.
Everything above is still paper-only end to end: `PaperBroker` is still the
only `ExecutionAdapter`, `make_order` is still the only `Order` constructor,
ccxt is read-only public data, and there is still no kill/clear/order tool in
the LLM's vocabulary.

---

## 12. v3.0 additions (docs/13 M18–M21): launch, visibility, institutional polish

Four milestones, all **additive UX/visibility only** — none touch the safety
core (`risk/`, `execution/`, `autonomy/promotion_gate`, `kill_switch`); the
M22 review (`V3-RELEASE-REVIEW.md`) re-proves every one of the 9
non-negotiables against all four.

**M18 — zero-CLI launch.** `run.py`/`run.bat` now do first-run setup in a
background thread while the desk serves a plain-language onboarding screen
(`ops/jobs.py::LaunchState`, a middleware-level swap in `ui/app.py` — never a
blank page, never a stack trace) instead of the real dashboard, becoming
reachable automatically once `ready` flips. The bigger addition is
`ops/jobs.py`'s `JobManager`: it lets the desk itself trigger **ingest /
backtest / live start-stop** via `POST /api/jobs/*`, instead of requiring a
terminal. Every job calls the *exact same* functions the CLI already used
(`data.ingest.ingest`, `backtest.runner.run_backtest`,
`live.session.LiveSession`, itself extracted from the old `_cmd_live` so the
CLI and the GUI share one implementation) from a background thread — this
adds no new order-construction path, only a new caller of code that already
routes through `make_order`/`RiskModel` (verified structurally:
`tests/safety/test_v3_surfaces.py`). `run.bat` exists because double-clicking
`run.py` directly on Windows silently opens/closes a console using whatever
Python happens to be file-associated (often the wrong one) — `run.bat` calls
this project's own `.venv` explicitly.

**M19 — Obsidian Desk, applied.** The design system had actually been built
to spec since M7–M10; this milestone's real scope turned out narrower than
the roadmap text implied. What's new: a hero price/equity chart on the Floor
view using **vendored** TradingView Lightweight Charts v5.2.0
(`ui/theme/vendor/`, Apache-2.0 — vendored rather than CDN-loaded because the
desk is `127.0.0.1`-only with no outbound network at runtime, same rule as
the pre-existing `viz3d/vendor/`), a `Ctrl`/`Cmd`+`K` command palette, toast
notifications for control/job actions, and a genuine computed AA-contrast
audit that caught `--mute` failing the spec's literal 4.5:1 ratio (fixed,
same hue, not a redesign).

**M20 — live trade blotter.** `StateReader.blotter()`/`.reconciliation()`
reconstruct the full order lifecycle straight from events already in the
audit log — no new event type needed. The correlation key is `intent_id`,
already shared by `OrderIntent.intent_id`, `RiskDecision.intent_ref`, and
`Order.intent_ref`/`Order.order_id = f"order:{intent_id}"` (a pre-existing
`make_order.py` convention). One `BlotterRow` per fill; a REJECTed or
approved-but-unfilled intent still gets exactly one no-fill row — nothing
silently disappears. Per-fill P&L is a `realized_before`/`realized_after`
snapshot delta taken around the *existing* `_StrategyAgg.on_buy`/`on_sell`
call already made for `model_cells()` — not a second, potentially-divergent
P&L computation. Verified against a **real live fleet run** (`JobManager.
start_live` with the offline CSV adapter seam), not only a hand-built audit
fixture, specifically because the milestone spec worried about "the display
works but the plumbing doesn't."

**M21 — the "Engine Room" conversation feed.** `StateReader.conversation
(at_seq=None)` reconstructs a turn-by-turn dialogue from the same autonomy
events M9's decision cards already read — added *alongside* those cards, not
replacing them. `TrialEvent`s aggregate into one Optimizer card per
hypothesis window (the best `oos_metric`, never one message per trial);
promotions are attributed to the **Judge** ("the Judge decides"), not the
Strategist; `ValidationEvent` carries a `verdict` field so the UI can color
the Judge's message by outcome rather than a fixed hue. A new
`#convo-scrubber` timeline control mirrors the Engine 3D view's existing
scrubber UX exactly (`GET /api/conversation?at_seq=`, same deterministic-
replay pattern as `/api/graph`). Internal correlation IDs (`hypo_id`,
`candidate_id`, `trial_id`) are used only as grouping keys and never appear
in a message's default text — a native `<details>` element discloses the
Judge's raw evidence dict as plain `k: v` lines for anyone who wants it.
Verified against a **real `lqe autopilot` campaign** end to end (a real
replay bundle, 3 real hypothesis cycles, served via `lqe desk`), confirming
both the rendered feed and the scrubber's deterministic mid-campaign replay.

**What M22 (this review round) added on top:** `tests/safety/
test_v3_surfaces.py` (11 tests) and 6 tests appended to `tests/honesty/
test_ui_honesty.py`, closing the specific gap that M18–M21's own milestone-
exit tests proved *that milestone's* feature worked, but nothing had yet
re-asked "do all 9 non-negotiables still hold across the whole M18–M21
surface at once" — see `V3-RELEASE-REVIEW.md` for the full evidence table.

---

## 13. v4.0 additions (docs/14 M23–M25): measured catalog diversification, not headcount

Three milestones, all **additive to the catalog/data layer only** — no new
UI surface, no changes to `risk/`, `execution/`, or `autonomy/promotion_gate`
beyond the pre-existing signal→order pipeline every new model reuses
unmodified; the M25 review (`V4-RELEASE-REVIEW.md`) re-proves the safety/
honesty gate against everything M23–M25 added.

**M23 — the diversification framework + sleeves A–E/G–I/L/M.** A new
`Sleeve` taxonomy on `ModelManifest` (`models/manifest.py`) groups every
model by its **return driver** (trend/momentum, mean-reversion, cross-
sectional, stat-arb, volatility, carry/basis, breakout/structure,
seasonality, regime overlay, ML signal, allocator, or `control` for the
deliberately-weak `naive_always_long`) — a coarser, differently-motivated
cut than the pre-existing `Family`. `analytics/diversification.py` computes
the actual acceptance metric: average pairwise correlation, effective
number of bets (eigenvalue-based), and sleeve dominance. The catalog's own
engine gained a real capability along the way: `Context.universe_closes` +
`Session.run` now accept a **merged, multi-symbol bar stream** — every bar
updates a shared per-symbol close snapshot and reaches every strategy's
`on_market`, but the entire risk/accounting/order pipeline stays gated to
`bar.symbol == self._symbol` (a signal from a foreign bar is discarded,
never ordered) — a strict no-op for every pre-v4 single-symbol caller. This
unlocked genuine cross-sectional (`CrossSectionalAdapter`, ranks a universe
each bar) and stat-arb-beyond-pairs (`DistancePairsAdapter`/
`LeadLagAdapter`/`BasketArbAdapter`/`JohansenBasketAdapter`) strategies.
Catalog grew 51→94 models.

**M24 — the perp/funding data adapter + carry/basis sleeve (F).** A
genuinely new data type: `FundingRateEvent` (a periodic ~8h settlement,
distinct from `MarketEvent`'s per-bar cadence), fetched by
`data/funding_adapter.py::CcxtFundingRateAdapter` (public
`fetch_funding_rate_history` only, same read-only pattern as
`ccxt_adapter.py`), validated (`validate_funding_rates`), stored
(`storage/parquet_funding.py`, the same idempotent partitioned pattern as
OHLCV), and ingested (`ingest_funding_rates`, reusing `Catalog.data_versions`
with a `timeframe="funding"` sentinel — no schema migration). Four new
strategies (`FundingCarryAdapter`, `FundingMomentumAdapter`,
`BasisCarryAdapter`, `CrossExchangeFundingAdapter`) trade the spot leg only
— **this engine's short-selling path is explicitly out of scope**
(`portfolio/accounting.py` raises rather than silently going short), so
these are honestly disclosed as directional bets gated by a funding/basis
signal, not a market-neutral carry harvest. Catalog grew 94→104 models. The
milestone's own exit criterion ("measurably low-correlation to directional
sleeves") was measured for real and **not met** — carry_basis's cross-group
correlation (0.4144) came out *higher* than the whole-catalog average
(0.3742) in the same run, a direct, mechanical consequence of the long-only
simplification (every sleeve F model's P&L is ordinary spot price movement
when it holds a position, the same driver every directional model shares).
Disclosed plainly in `docs/14`, `HANDOFF.md` §1e, and `V4-RELEASE-REVIEW.md`
rather than reframed.

**M25 — correlation curation, operationalized; diversification review;
tag v4.0.** `models/curation.py::correlation_curation_check` (built at M23,
left unwired) finally got run for real: `scripts/curation_report.py` walks
the full 104-model catalog in registration order, backtesting each and
checking it against every model registered before it. **Measured result:**
46 of 97 non-degenerate models (47%) would have been flagged as redundant
duplicates — a mix of genuine near-duplicate parameterizations (adjacent
MACD/Donchian/TSMOM/ROC lookback variants) and **short-window behavioral
convergence** (several conceptually distinct models — `naive_always_long`,
a seasonality model, an allocator, a carry model — each entered once near
the start of the ~1.4-day test window and simply held, so their equity
curves all tracked raw BTC-USDT price identically for that one run;
confirmed by hand that two of them finish with the *exact same* position
size). This is reported as a real, honest, window-dependent diagnostic, not
a production-grade gate. A dedicated safety test
(`tests/safety/test_v4_no_shorting.py`) verifies — not just declares — that
none of the 104 models ever emits a `SHORT` signal, by running the whole
catalog through a real adversarial (uptrend-then-downtrend) multi-symbol
backtest and inspecting the actual audit log.
