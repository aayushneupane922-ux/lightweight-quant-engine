# Developer Handoff — `lightweight-quant-engine`

**Current state: v2.0, fully shipped.** This document is a complete, standalone
briefing for a developer picking this project up for the first time — what it
is, what's been built, how it's built, what it guarantees, and what's known to
be missing. It ends with a specific ask: **propose the upgrade roadmap for
what comes next**, since none exists past v2.0 in any doc.

---

## 1. What this is

A **local, paper-only, autonomous quant-research simulator**. It runs entirely
on one machine, serves a browser UI on `localhost` only, costs effectively
$0/month to run, and — by construction, not just by configuration — **cannot
place a real trade, connect to a real broker, or claim a trading profit.**

The pitch: a large catalog of quantitative/statistical trading models runs
continuously against real-time crypto market data in full simulation. An
**LLM + classical-ML "engine room"** runs a continuous learn → validate →
promote loop over that catalog — proposing parameter ranges, searching them
with Optuna, judging every candidate against an out-of-sample statistical
gate — with an aggressive, always-on **autopilot** and a live-updating web
dashboard (the "Obsidian Desk") to watch it work.

**The one sentence that matters:** the system *learns* on historical data,
runs only *validated* results against live data, watches live performance for
decay, and re-learns on history when it decays — the LLM steers and narrates,
the math (walk-forward validation + Deflated Sharpe + Probability of
Backtest Overfitting) decides what's real.

---

## 2. The non-negotiables (why this is safe to run)

These are structural, not configuration flags — every one is enforced by an
automated test, most by an AST-level scan of the codebase, not just a runtime
check:

1. **Paper-only.** `PaperBroker` is the *only* class that implements the
   execution-adapter interface (a test scans the whole repo to confirm this).
   No real broker SDK is imported anywhere. `LIVE_TRADING_ENABLED = False` is
   a hardcoded constant with no code path that flips it.
2. **One order-construction choke point.** Exactly one function
   (`make_order`) can ever construct an `Order` object, and it can only be
   called after a risk-gate decision. This is enforced by an AST scan, not
   just convention — a test literally parses the codebase looking for any
   other `Order(...)` construction.
3. **Config rejects live trading by name.** Loading a config with
   `mode: live` fails immediately and by design, not by accident.
4. **A human-owned kill switch.** Disk-persisted, survives a restart, never
   auto-clears, and can only be cleared by a named human operator. The LLM
   has no "clear kill switch" or "place order" tool in its vocabulary at
   all — it's not blocked by a permission check, the capability simply
   doesn't exist for it to call.
5. **Full determinism + audit.** Every single thing that happens is an event
   appended to a hash-chained, tamper-evident audit log. Two runs with
   identical inputs and seed produce byte-identical audit hashes. Sessions
   can be replayed from the log exactly.
6. **A real promotion gate.** Nothing is ever labeled `validated` except by
   passing walk-forward out-of-sample validation, a Deflated Sharpe Ratio
   check, a Probability-of-Backtest-Overfitting check, a transaction-cost
   sensitivity sweep, and beating simple benchmarks (buy-and-hold,
   equal-weight, random-entry). Breadth of models never substitutes for this.
7. **Sandbox vs. tracked, never conflated.** Aggressive, unvalidated
   exploration happens in a "sandbox" and is clearly labeled `unproven`
   everywhere in the UI; only gate-passed configs reach the "tracked" book
   that the equity curve you watch is built from.
8. **No profit claims, anywhere.** The UI and every generated report carry
   "simulated," sample-size, and unproven/validated labeling; there is no
   language anywhere claiming or implying a real trading edge.
9. **A fail-closed license gate.** CI walks the full transitive dependency
   tree of everything actually shipped and fails the build if any dependency
   carries a disallowed (e.g. GPL/AGPL) license — unknown licenses fail
   closed rather than being silently allowed.

---

## 3. Architecture at a glance

```
 ingest (ccxt, public data only, or CSV replay)
        │
        ▼
 curated Parquet + DuckDB catalog → checksummed, frozen "replay bundle"
        │
        ├──────────────┬───────────────────┐
        ▼              ▼                   ▼
   lqe backtest   lqe autopilot        lqe live
 (one strategy,   (search+validate+   (the WHOLE catalog,
  one pass)        promote loop,       one paper book per
                    looped)             model, real-time or
                                         replayed data, autonomy
                                         loop narrating live)
        │              │                   │
        └──────────────┴───────────────────┘
                        ▼
         hash-chained AuditLog (JSONL, tamper-evident)
                        │
                        ▼
          StateReader (pure read-only replay of the log)
                        │
                        ▼
        Obsidian Desk — FastAPI + WebSocket, 127.0.0.1 only
     Floor · Catalog · Research · Intel · Engine (3D) · Risk · Daily
```

**Tech stack** (deliberately minimal, all vetted for license + no external
services): Python 3.12, Pydantic, ccxt (market data only), DuckDB + Parquet,
NumPy (self-built statistics — no scipy/pandas dependency for the core math),
Optuna (hyperparameter search), FastAPI + Jinja2 + native WebSocket (the UI —
NiceGUI was evaluated and rejected for license reasons), a dependency-free
`<canvas>` force-graph for the 3D visualization (three.js was evaluated and
rejected — not vendorable in an offline/no-CDN build), and an **optional**
local Ollama LLM reached over loopback HTTP via the Python standard library
(no new dependency; the system is fully functional with the LLM absent — it
falls back to a deterministic, templated narrator).

---

## 4. What's built — v1.0 (`docs/10-production-roadmap.md`, milestones M0–M12)

| Milestone | What it delivered |
|---|---|
| M0 | Repo scaffold, tooling (ruff/mypy/pytest), CI, license gate |
| M1 | Deterministic core: hash-chained audit log, clock abstraction, the paper-only lockout, `make_order` as sole constructor |
| M2 | Data ingest (ccxt + CSV), OHLCV data-quality validation, Parquet/DuckDB storage, checksummed replay bundles |
| M3 | Backtest runtime: paper broker, fills/slippage/commission, Decimal-precision accounting, position sizing |
| M4 | **The promotion gate** — walk-forward validation, Deflated Sharpe, Probability of Backtest Overfitting, cost sensitivity, benchmark comparison. *This is the real product.* Tagged **v0.1**. |
| M5 | Risk model (12 rules), the human kill switch, reconciliation + crash recovery |
| M6 | The model catalog: manifest schema, intake/quarantine process, 11 models across trend/momentum/mean-reversion/volatility |
| M7 | The Obsidian Desk web UI — Floor, Catalog, Research, Risk, Daily views, read-only state reconstruction, the one whitelisted write path (kill/freeze) |
| M8 | The autonomy loop: OBSERVE → HYPOTHESIZE → SEARCH → VALIDATE → DECIDE → NARRATE, Optuna-driven, fully audited |
| M9 | Autopilot + optional local LLM narrator, fail-closed tool-call parsing (5 whitelisted tools only — no order/kill/validate capability exists for the LLM) |
| M10 | The 3D "neural web" visualization with deterministic timeline replay |
| M11 | Scaled the catalog to 51 models via adapter presets, added multi-instrument accounting |
| M12 | Hardening: health check (`lqe doctor`), backups, packaging, the full safety/honesty review with evidence (`M12-RELEASE-REVIEW.md`). Tagged **v1.0**. |

**v1.0 = a complete, working local product.** Every milestone above is
committed and tagged (`m0-done` … `m12-done`, `v0.1`, `v1.0`).

## 5. What's built — v2.0 (`docs/12-v2-roadmap.md`, milestones M13–M17)

After v1.0 shipped, real usage surfaced three follow-on needs, which became
the v2.0 roadmap:

| Milestone | What it delivered |
|---|---|
| M13 | **Completed the model catalog to 51/51** (was 48/51) — installed the 3 remaining statistical/portfolio libraries that had been blocked by a Windows filesystem limit |
| M14 | **`lqe live` became a first-class, tagged CLI command.** Every admitted model (all 51) runs as its own independent paper book, sharing one audit log and one kill switch, fed by continuously-polled real market data (or a local file, for offline demos/tests). The autonomy loop narrates live on the dashboard. *Along the way, running the full 51-model fleet for real for the first time surfaced and fixed a genuine bug in one of the portfolio-optimizer models.* |
| M15 | **Crash/restart resilience.** `lqe live --out <path>` persists the trading state; running the identical command again automatically and verifiably resumes exactly where it left off (positions, cash, working orders, risk state) — proven byte-identical across a real restart, not just "close enough." |
| M16 | **Real automated test coverage for the LLM path**, plus a second CI pipeline that installs the full statistical/ML library set so those code paths are continuously verified, not just checked once manually |
| M17 | Documentation brought current, the full safety/honesty review re-run and re-certified (`V2-RELEASE-REVIEW.md`), tagged **v2.0** |

**v2.0 = the same product, hardened for continuous/unattended operation and
with its previously-manual verification steps automated.**

---

## 6. How to run it

```bash
pip install -e ".[ui,search,dev]"      # the running product + dev tools
lqe doctor                              # read-only health check
python run.py                           # serve the dashboard on 127.0.0.1
```

To see the whole catalog trade live against real market data:
```bash
lqe live --llm --llm-model llama3.2:3b --out runs/session.jsonl
```

Full instructions: `USER-GUIDE.md`. Deep technical dive on every component:
`COMPONENT-GUIDE.md`. To verify everything from scratch:
```bash
pytest -q && ruff check . && mypy src && python scripts/license_gate.py
```
Current result: **312 tests pass, 8 skip correctly** (skips are all
environment-conditional — e.g., a real-LLM test that only runs when a local
Ollama server happens to be up), lint clean, types clean (strict mode),
license gate clean.

---

## 7. Known limitations (told plainly, not glossed over)

- **`lqe live --out` resume does not restore the autonomy/promotion
  history** — only the trading fleet's positions/cash/orders. A resumed
  session's search-and-validate loop starts a fresh campaign. Extending
  resume to cover that too is a real, scoped piece of future work.
- **The new CI pipeline for the full statistics/ML library set has never
  run on a live CI server** — this repository has no remote git host
  configured, so it's been validated locally (config syntax + an equivalent
  local run) but not proven on an actual GitHub Actions runner.
- **If a human toggles the kill switch during the exact gap between a crash
  and a restart**, the resumed session uses the *current* kill-switch state
  going forward — a narrow edge case, and never something the automation
  itself can trigger.
- **The autopilot's default search surface (3 models) is much narrower than
  the full catalog (51 models)** — `lqe live`'s autonomy loop searches a
  broader 10-model surface, but neither covers the full 51 yet. Widening
  this further is a candidate next step.
- **The "Research" dashboard view needs manual wiring** to show persisted
  experiment history — supported by the underlying code, not yet plumbed
  through the CLI.
- No formal roadmap exists past v2.0 in any project document.

None of the above touch or weaken any of the 9 safety non-negotiables in
§2 — they are scope/UX gaps, not safety gaps.

---

## 8. Where to look for more detail

| Document | What's in it |
|---|---|
| `README.md` | Top-level orientation + links to every spec doc |
| `USER-GUIDE.md` | How to run every command, as a user |
| `COMPONENT-GUIDE.md` | Deep dive: what every module does, why, and the two-catalog/two-CI-lane gotchas worth knowing before you touch this code |
| `docs/00`–`11` | The original design specification (vision, architecture, autonomy loop, model catalog, validation protocol, UI/3D spec, engine/risk/audit spec, cost/LLM stack, the v1.0 build plan) |
| `docs/10-production-roadmap.md` | The v1.0 milestone-by-milestone build roadmap (M0–M12), fully executed |
| `docs/12-v2-roadmap.md` | The v2.0 milestone-by-milestone build roadmap (M13–M17), fully executed, with per-milestone evidence of what was tested and verified |
| `M12-RELEASE-REVIEW.md` / `V2-RELEASE-REVIEW.md` | The formal safety/honesty review, with file/test/command-level evidence, for v1.0 and v2.0 respectively |
| `GUARDRAILS.md` | The hard boundary fence — what must never be done, and when to stop and ask a human |
| `HANDOFF.md` | The internal, terser continuity note (written for picking this project back up quickly, not for external readers) |

---

## 9. What we're asking of you

This project has now shipped two complete, reviewed, tested milestone
roadmaps (v1.0 and v2.0) with nothing left on either one. **There is no
defined roadmap past this point.**

We'd like you to review everything above (and the deeper docs it points to)
and **propose an upgrade roadmap** — what should come next, in what order,
and why. Some open threads from v2.0 that surfaced naturally (listed in §7)
are candidates, but we'd like your independent read on priority, sequencing,
and anything we haven't thought of, rather than treating that list as fixed
scope. Whatever's chosen, we've been building milestone-by-milestone with
tests-first discipline and a tag at every exit gate (`git tag mN-done`) — the
next roadmap should be able to follow the same pattern.
