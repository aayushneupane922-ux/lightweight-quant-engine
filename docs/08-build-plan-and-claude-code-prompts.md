# 08 — Build Plan & Claude Code Prompts (FINAL)

The developer builds from this. Additive, milestone-by-milestone; each ends in a review + the safety/honesty gate. Deep prior prompts are in [`archive/`](archive/) (16–19, 27, 31) for reference; **this is the current plan.**

## 8.1 Repo shape (fresh)
```
lightweight-quant-engine/
├── CLAUDE.md                     # agent context (final)
├── pyproject.toml  .gitignore  THIRD_PARTY_NOTICES.md
├── docs/                         # 00..09 (this fresh set) + archive/
├── config/  engine.example.yaml  risk.example.yaml  autopilot.example.yaml
├── src/lqe/
│   ├── core/        events clock bus engine context determinism make_order constants
│   ├── data/        ccxt_adapter csv_replay ingest validate symbols
│   ├── storage/     parquet catalog replay_bundle
│   ├── models/      base + native plugins + adapters (pandas_ta, skfolio, statsmodels, arch, riskfolio…)
│   ├── portfolio/   accounting sizing
│   ├── risk/        model rules kill_switch      # tunable-in-sim, audited
│   ├── execution/   paper_broker fills slippage commission _locked_out
│   ├── autonomy/    orchestrator optimizer(optuna) validator promotion_gate drift(river) narrator(llm) rules_fallback
│   ├── analytics/   metrics dsr pbo tearsheet registry
│   ├── backtest/    runner make_session
│   ├── live/        sandbox_book tracked_book daemon control
│   ├── ui/          app(fastapi+nicegui) views/  state(read-only)  theme/(obsidian-desk)
│   ├── viz3d/       neural_web (three.js/3d-force-graph payload builder) 
│   └── cli.py
└── tests/  unit/ property/ parity/ safety/ honesty/ integration/
```

## 8.2 Milestones (build order)
| M | Delivers |
|---|---|
| 1 | Deterministic core + **paper-only lockout** + audit hash-chain + `make_order` choke point + config (rejects live) |
| 2 | Crypto data ingest/validate → Parquet/DuckDB + replay bundles |
| 3 | Model runtime + PaperBroker (pessimistic fills) + accounting + 1 model; backtest runner + `make_session` |
| 4 | Validation stack: walk-forward, **DSR/PBO**, cost sweep, benchmarks, experiment registry (**the promotion gate**) |
| 5 | Risk model (tunable-in-sim, audited) + human kill/freeze + reconciliation + rebuild-from-audit |
| 6 | Model catalog + adapters (pandas-ta/skfolio/statsmodels/arch/riskfolio) + intake/quarantine → ≥10 models |
| 7 | **Obsidian Desk** web UI (localhost, no-CLI) — Floor/Catalog/Research/Risk + honesty layer |
| 8 | **Autonomy loop**: Orchestrator + Optuna optimizer + Validator + PromotionGate + River drift → sandbox↔tracked, de-risk-on-degradation (rule-based first) |
| 9 | **Autopilot** (aggressive) toggle + decision cards + tracked/sandbox separation; **Local LLM narrator/orchestrator** (Ollama) with rule-based fallback |
| 10 | **3D neural-web** visualization (three.js/3d-force-graph) from audit state + timeline replay |
| 11 | Scale catalog to 50+ (advanced statistical: cointegration/GARCH/HMM/Bayesian allocation) + portfolio/pairs |
| 12 | Safety, honesty & determinism review + license CI gate + docs update |

**Thin slice for a fast, usable system:** M1→M3→M4→M8 gives the honest learning loop headless; add M7 then M9→M10 for the terminal + autopilot + 3D. M4 (the gate) must exist before any autonomy (M8) — never let the loop run without the judge.

## 8.3 Safety/honesty gates (hold every milestone)
Paper-only lockout green · every order through `make_order` after the risk model · one `Order` constructor · human kill un-overridable by the LLM · **PromotionGate cannot be bypassed by the LLM/autopilot** · trial-counting feeds DSR/PBO · GUI renders no CLI/stdout · sandbox vs tracked never conflated · determinism/replay + audit hash-chain verify · runtime license gate green · no profitability claims.

## 8.4 Master prompt (paste as `CLAUDE.md` / at session start)
```
You are building `lightweight-quant-engine`: a LOCAL, PAPER-ONLY, autonomous quant research
simulator. Engine runs locally; GUI is served on 127.0.0.1 in a browser. An LLM+ML "engine
room" runs a learn→adjust→learn loop over a large model catalog, with an aggressive AUTOPILOT,
and a 3D neural-web visualization. Build by milestone (docs/08); STOP for review after each.

NON-NEGOTIABLES
1. Paper-only. No real orders, no broker SDK, no credentials. PaperBroker is the only
   ExecutionAdapter (is_paper=True asserted at startup). LIVE_TRADING_ENABLED=False, no flip;
   config rejects live mode.
2. Full audit + determinism: every event AND every autonomy action (hypothesis/trial/validation/
   promotion/de-risk/LLM prompt+response) is hash-chain logged; execution is deterministic per
   config+seed; sessions REPLAY from the log. This makes the aggressive autonomy honest.
3. Promotion gate: no config reaches the TRACKED book until it passes out-of-sample validation
   (walk-forward + Deflated Sharpe + PBO + cost survival + beats equal-weight/random). The LLM
   explores freely in the SANDBOX and cannot mark anything 'validated' — only the Validator can.
4. Two surfaces: SANDBOX (aggressive, unvalidated) vs TRACKED book (validated only, de-risks on
   degradation, never chases the curve). Never conflate them in code or UI.
5. The LLM ORCHESTRATES + narrates; Optuna does the numerical search; the Validator judges.
   The LLM never does the optimization and never overrides the gate. Its actions are logged.
6. Human KILL/freeze is un-overridable by the LLM. Autopilot is aggressive but paper-only + audited.
7. GUI renders NO CLI/stdout — structured components only. localhost only; no auth; no network.
8. Runtime deps MIT/BSD/Apache/NCSA only (license CI gate). Models are deterministic + manifest-
   complete or they're quarantined.
9. No profitability claims anywhere. "Equity going up" only ever means the tracked, gate-passed,
   out-of-sample, after-cost book — labeled with its validation provenance.

STACK: Python 3.12, ccxt, duckdb+polars+pyarrow, pandas/numpy, pandas-ta, statsmodels/arch/
hmmlearn/ruptures, skfolio/PyPortfolioOpt/riskfolio, sklearn/LightGBM/River/Optuna, pydantic,
FastAPI+NiceGUI, three.js+3d-force-graph, Ollama (optional), pytest+hypothesis, ruff+mypy.

DEFINITION OF DONE (every change): ruff+mypy clean; unit+property+parity+safety+honesty tests
green; audit hash-chain verifies; PromotionGate un-bypassable; GUI has no CLI; license gate green;
docs updated. Prefer the smaller, safer, more deterministic option. STOP for review each milestone.

FIRST ACTION: read docs/00,01,02,04,06,08; implement Milestone 1 (deterministic core + paper-only
lockout + audit) with tests; STOP for review.
```

## 8.5 Per-milestone prompt pattern (use for M2..M12)
```
Implement Milestone <n>: <deliverable from §8.2>, per docs/<refs>. Write tests first where
practical (incl. safety/honesty). Preserve every §8.3 gate. For autonomy/UI/3D milestones:
prove the PromotionGate can't be bypassed, the GUI shows no stdout, sandbox≠tracked, and the
human kill can't be disabled by the LLM. Run the full suite + docs/archive/19 §19.1 safety
review + the honesty checklist. Summarize what changed and why. STOP for review.
```
