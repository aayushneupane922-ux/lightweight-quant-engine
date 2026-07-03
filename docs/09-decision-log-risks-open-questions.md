# 09 — Decision Log, Risks & Open Questions (FINAL)

## 9.1 Decisions (settled; build treats these as fixed)
| # | Decision | Why | Confidence |
|---|---|---|---|
| D1 | Local engine + `localhost` web GUI (not a native binary) | keeps the full Python/JS stack; simplest local-first path | High (owner) |
| D2 | Autonomous **LLM orchestrator + Optuna + Validator** | LLM good at *what to try* + explaining; Optuna does the search; validation judges ([AgentHPO](https://arxiv.org/abs/2402.01881)) | High |
| D3 | **Aggressive autopilot**, sim-only | owner's call; no financial harm in simulation | High (owner) |
| D4 | **Promotion gate** (OOS validation) between sandbox and tracked book | the one thing that keeps the watched curve from being an overfit | High |
| D5 | Degradation → **de-risk + re-validate**, never chase the live curve | owner-chosen; avoids automated overfitting | High (owner) |
| D6 | Keep **paper-only + full audit/determinism** as hard rails | paper-only stops financial harm; audit makes autonomy honest/replayable | High |
| D7 | Big catalog via **adapters**, discipline via **trial-counting** | breadth is a research surface; the gate makes size safe | High |
| D8 | 3D neural-web via **three.js/3d-force-graph** from real audit state | honest telemetry, not a fake brain ([3d-force-graph](https://github.com/vasturiano/3d-force-graph)) | High |
| D9 | Local **Ollama** LLM optional; rule-based fallback | $0, private; system works without it | High |
| D10 | Crypto-first data (free), asset-agnostic core | free real-time for the live sim | High (owner) |

## 9.2 Corrections on record (premises addressed)
- [Certain] "Keep the equity curve going up and up with min drawdown" is **not an achievable objective** — a loop chasing recent performance overfits. Resolved by D4/D5 (validated promotion; de-risk not chase).
- [Certain] "More/bigger models = more robust" is **false**; robustness = out-of-sample survival + parsimony. Resolved by D7 (trial-counting into DSR/PBO).
- [Certain] An LLM is a poor numerical optimizer/authority; resolved by D2 (LLM orchestrates, Optuna searches, Validator judges).

## 9.3 Top risks (ranked)
1. **Automated overfitting** — an aggressive searcher manufacturing fake curves. Mitigation: the PromotionGate + honest trial-counting (docs/04). *The single most important control.*
2. **Sandbox/tracked confusion** — mistaking exploratory churn for validated performance. Mitigation: hard separation in code + UI + 3D.
3. **LLM overreach / nondeterminism** — unpredictable actions. Mitigation: structured tool calls, low temp, actions logged, gate un-bypassable, human kill.
4. **Trust illusion from the 3D viz** — cinematic UI implying more skill than exists. Mitigation: honesty overlays, honest telemetry not a fake brain.
5. **Compute blow-up** — aggressive search saturating the machine. Mitigation: bounded job queue, throttles (compute is the natural limit, by design).
6. **Look-ahead/survivorship** slipping into the loop. Mitigation: data hygiene (docs/04 §4.3), causal features, replay parity.
7. **Local LLM weight licensing** if ever distributed. Mitigation: verify model license before distribution (docs/07).
8. **Scope/motivation** — large build. Mitigation: thin slice M1→M3→M4→M8 first (docs/08).
9. **Determinism regressions** from concurrency/LLM. Mitigation: replay-equality + parity tests in CI.
10. **Paper→reality gap** if ever tempted toward live — out of scope by hard rail; would need a separate, reviewed track.

## 9.4 Open questions (decide as you build)
1. Sandbox compute budget / max concurrent trials (autopilot tempo cap)?
2. Which local LLM to standardize on (Llama 3.1 8B vs Qwen 3 8B vs larger)? Start 7–8B.
3. Promotion-gate thresholds (min DSR, max PBO, min trades) — pre-commit them.
4. Tracked-book composition: single promoted config, or an ensemble of promoted models (equal-weight of survivors is a strong default)?
5. Regime characterizer depth (trivial vol/trend vs HMM) — start trivial, ablate.
6. 3D viz fidelity vs performance ceiling on your GPU?
7. First exchange to standardize on (Binance/Kraken/Coinbase)?

## 9.5 Verify before spending money
1. Confirm the free crypto data path meets your timeframes (pull + validate) before any paid feed.
2. Re-check Claude Code pricing/limits for your usage (drifts).
3. Prove the loop + gate on free data before renting GPU compute for faster search.
4. Re-run the license CI gate before assuming the runtime is clean for distribution; verify local-LLM weight licenses before shipping anything.
5. Any move toward live trading = a separate, professionally-reviewed track (out of scope here).

## 9.6 What "done" means for this product
An autonomous, aggressive, **paper-only** learn→adjust→learn simulator: a large honest catalog, an LLM+Optuna+Validator loop that promotes only out-of-sample survivors, an autopilot you can ride, a 3D neural-web you can watch, full audit/replay — and **zero** ability to place a real trade or claim a profit.
