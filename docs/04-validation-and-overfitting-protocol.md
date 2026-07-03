# 04 — Validation & Overfitting Protocol (FINAL — the real product)

> With an **autonomous, aggressive** loop tuning a **large** catalog, the overfitting risk is *higher*, not lower — an automated searcher is the perfect machine for producing beautiful, fake equity curves. This protocol is the promotion gate that stands between exploration and self-deception. It is the actual product; everything else is plumbing.

## 4.1 The promotion gate (what stands between sandbox and tracked book)
A candidate config may be **promoted** to the tracked book only if it passes **all**:
1. **Walk-forward out-of-sample:** stitched OOS performance across rolling re-fits (not one lucky split). ([Pardo lineage](https://arxiv.org/pdf/2512.12924))
2. **Deflated Sharpe Ratio > 0** given the *honest trial count* (every Optuna trial + every model tried, across the whole catalog). ([Bailey & López de Prado](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551))
3. **Acceptable PBO** (probability of backtest overfitting) via combinatorially-symmetric CV. ([PBO](https://www.researchgate.net/publication/318600389_The_probability_of_backtest_overfitting))
4. **Survives realistic costs** (cost-sensitivity sweep 0/5/10/20 bps; edge intact after costs).
5. **Beats the honest benchmarks** at equal turnover after costs: buy-and-hold, **equal-weight**, best-single-model, and a **random-entry control**.
6. **Purged & embargoed CV** for any ML/meta-model (no leakage across the overlapping-label boundary; López de Prado).
7. **Deterministic replay** reproduces the candidate's trades bit-for-bit.

Fail any → not promoted; the LLM logs the killed hypothesis and learns. This is enforced in code as `PromotionGate.check(candidate) -> PASS/FAIL + evidence`; the LLM cannot set `validated` itself.

## 4.2 Trial counting (the autonomy multiplier)
The autonomous loop can run thousands of trials — so **every** trial and model is counted and fed into DSR/PBO. Without this, aggressive search guarantees a false winner. The experiment registry (DuckDB) records every run's provenance (config, data version, git SHA, seed, metrics, trial index) so the count is automatic and auditable.

## 4.3 Data hygiene (or the gate is meaningless)
- **Fixed splits by date**, test set touched once. Purge/embargo boundaries.
- **No look-ahead:** act only on completed bars; causal features; UTC left-edge bars.
- **Survivorship-safe** universe (delisted kept). Validated on multiple regimes, not one period. Details: [`06`](06-engine-data-risk-and-audit.md).

## 4.4 Degradation & re-validation (live loop discipline)
When the tracked book degrades/flattens ([`02`](02-autonomy-autopilot-and-learning-loop.md) §2.4): de-risk first, then a fresh search must **re-pass the full gate** before any replacement is promoted. A model is **retired** from the tracked book (not just re-tuned) if it repeatedly fails re-validation.

## 4.5 "Kill the candidate if…" (auto-enforced)
No economic rationale · edge dies at realistic costs · parameter spike not plateau · DSR ≤ 0 / high PBO on honest count · hinges on few trades/one period · fails walk-forward OOS · can't beat equal-weight/random at equal turnover · look-ahead/survivorship suspected · live replay ≠ backtest · performance-chasing signature (weights just track trailing returns). The gate encodes these; the LLM sees the kill reason and adapts.

## 4.6 What "the equity curve going up" is allowed to mean
Only this: **the tracked book, composed solely of gate-passed configs, evaluated out-of-sample, after costs.** A rising sandbox curve means nothing (it's unvalidated). The UI must always distinguish the two ([`05`](05-ui-and-3d-visualization.md)), and label the tracked curve with its validation provenance.

## 4.7 Acceptance criteria
- `PromotionGate` enforces §4.1 in code; the LLM/autopilot cannot bypass it.
- Trial count spans all trials+models; DSR/PBO computed on the honest count; registry records provenance.
- Degradation triggers de-risk + full re-validation; repeated failure retires the model.
- Sandbox vs tracked performance are never conflated in the UI; tracked curve shows validation provenance.
