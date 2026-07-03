# 09 — Backtesting & Research Protocol

> **This file is the actual product.** A fast backtester in the hands of a solo dev is a machine for generating convincing lies. The controls here — not the engine — are what stand between you and confidently trading a curve-fit. Bailey & López de Prado proved that high simulated performance is *easy* after testing relatively few configurations, and that overfit strategies tend to **underperform** out-of-sample, not merely fail to outperform. ([Deflated Sharpe Ratio, SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551))

## 9.1 Hypothesis template (fill this BEFORE coding a strategy)

```
Hypothesis ID:  H-YYYYMMDD-nn
Author / date:
Economic rationale:   WHY should this edge exist? (behavioral, structural, risk-premium…)
                      "It backtests well" is NOT a rationale.
Instruments / market: (crypto pairs, timeframe)
Signal definition:    exact, causal, deterministic (no future data)
Entry / exit rules:   precise; include invalidation
Position sizing:      (fixed-fractional / vol-target) — see risk engine
Expected behavior:    when should it WIN? when should it LOSE? (falsifiable)
Failure prediction:   what regime kills it? (write it down now)
Benchmark:            buy-and-hold + equal-weight + random-entry control
Data range / splits:  train / validation / test (dates fixed up front)
Max # configs I will test: N   ← commit now; drives Deflated Sharpe
Kill criteria:        (from §9.9) — pre-commit the thresholds
```

If you can't state a **falsifiable failure prediction** and an **economic rationale**, you are curve-fitting, not researching.

## 9.2 Dataset selection & splitting

- **Fix splits by date, before any fitting.** Example: train `2019–2022`, validation `2023`, **test `2024–2025` (touched once)**.
- **Test set is sacred.** You may evaluate on it **once**, at the end. Every additional peek inflates your effective trial count and must deflate your Sharpe.
- **Purge & embargo** around split boundaries so overlapping-horizon labels don't leak across train/test (López de Prado). Essential for any ML or multi-bar-horizon signal.
- **Multiple instruments / regimes:** an edge should survive across several pairs and market regimes, not one lucky symbol-period.

## 9.3 Walk-forward analysis (the backbone)

Pardo's walk-forward is the default validation: re-fit (or re-select params) on a rolling in-sample window, evaluate on the immediately-following out-of-sample window, roll, repeat, and **stitch the OOS segments** into the performance you actually believe. ([walk-forward framework](https://arxiv.org/pdf/2512.12924))

- Report **only stitched out-of-sample** results as the headline.
- Anchored vs. rolling window: try both; instability across them is a red flag.
- **Combinatorial Purged Cross-Validation (CPCV)** (López de Prado) is the stronger upgrade for ML signals — *later*, once basics are solid.

## 9.4 Transaction-cost & slippage modeling (non-negotiable)

- Model **commission** (per-exchange bps), **spread**, and **slippage** explicitly. Default to *pessimistic*.
- **Fill assumption:** signal on completed bar `t`, fill at **next bar open** (or worse), never at the signal bar's close.
- **Cost-sensitivity sweep is mandatory:** re-run at 0/5/10/20 bps. If the edge dies at realistic costs, it was never an edge. This single check kills most naive strategies — cheaply.
- Keep the runtime fill model identical to backtest (shared code, [`05`](05-recommended-architecture.md) §5.4).

## 9.5 Liquidity, benchmark, and capacity

- **Liquidity filters:** skip illiquid pairs/bars where your assumed fill is fantasy (thin volume, wide spread).
- **Benchmarks:** always compare to (a) buy-and-hold, (b) equal-weight, and (c) a **random-entry / shuffled-signal control** with the same trade count and sizing. Beating a random control at the same turnover is the minimum bar.
- **Capacity:** estimate the size at which your own orders would move price / exceed a fraction of bar volume. A strategy that only works at toy size is a toy.

## 9.6 Metrics that matter (report all, worship none)

Use QuantStats/empyrical for computation. Report: CAGR, **Sharpe & Sortino**, **max drawdown & drawdown duration**, Calmar, hit rate, payoff ratio, **turnover**, exposure, tail ratio, and **the number of trades** (tiny-sample results are noise). ([QuantStats](https://github.com/ranaroussi/quantstats))

- **Drawdown analysis:** depth, duration, recovery, and *when* the worst DDs occur (regime). Path matters more than endpoint.
- **Turnover analysis:** high turnover multiplies cost sensitivity and shrinks capacity.

## 9.7 Overfitting controls (the core discipline)

1. **Count every trial.** Log *every* backtest/config you run on a dataset. Your effective number of trials `N` is the input to deflation.
2. **Deflated Sharpe Ratio (DSR).** Adjust the observed Sharpe for the number of trials, sample length, skew, and kurtosis. A high raw Sharpe from many trials can have a DSR near zero → not significant. ([DSR, Wikipedia](https://en.wikipedia.org/wiki/Deflated_Sharpe_ratio), [Bailey & LdP](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551))
3. **Probability of Backtest Overfitting (PBO)** via combinatorially-symmetric cross-validation: estimate the probability your "best" in-sample config underperforms the median out-of-sample. High PBO → discard. ([probability of backtest overfitting](https://www.researchgate.net/publication/318600389_The_probability_of_backtest_overfitting))
4. **Parameter-sensitivity map.** Plot performance across the parameter grid. Trust **broad plateaus**, distrust **isolated spikes**. A robust edge is insensitive to small parameter changes.
5. **Ablation testing.** Remove each component (a filter, the regime overlay, a feature) and re-test. If removing it doesn't hurt, delete it. Every surviving component must earn its place.
6. **Minimum trade count / minimum backtest length.** Pre-commit thresholds (e.g. ≥ some hundreds of trades, ≥ multiple years / regimes) below which results are "insufficient evidence," not "positive."

## 9.8 Paper-trading graduation criteria (backtest → paper)

A strategy may enter paper trading only if it **all** of:
- has a written economic rationale + falsifiable failure prediction (§9.1);
- survives **stitched walk-forward OOS**, not just a single split;
- has **DSR meaningfully > 0** given the honest trial count;
- has **acceptable PBO**;
- **survives the cost-sensitivity sweep** (edge intact at realistic bps);
- beats buy-and-hold, equal-weight, **and** the random-entry control at equal turnover;
- shows a **parameter plateau**, not a spike;
- passes **deterministic replay** (same inputs → same trades, bit-for-bit).

Graduation is recorded in the experiment registry with the evidence attached.

## 9.9 "Kill the strategy if…" checklist (pre-commit these)

Kill (or send back to research) if **any** are true:
- [ ] No economic rationale — it only "works" empirically.
- [ ] Edge **disappears at realistic costs** (0→10 bps flips it negative).
- [ ] Performance is a **parameter spike**, not a plateau.
- [ ] **DSR ≤ 0** / **PBO high** after honest trial counting.
- [ ] Results hinge on a **handful of trades** or one lucky period/symbol.
- [ ] Fails **out-of-sample / walk-forward** (great in-sample, poor OOS).
- [ ] Can't beat a **random-entry control** at the same turnover.
- [ ] Depends on data with **look-ahead/survivorship** you can't rule out.
- [ ] **Live/paper replay ≠ backtest** (non-deterministic or path-divergent).
- [ ] Requires **capacity/liquidity** your target market can't provide.
- [ ] You had to **peek at the test set** more than once to get here.
- [ ] Paper trading **materially underperforms** the backtest over a fair window.

Killing strategies is the job. Expect to kill the large majority. That's success, not failure.

## 9.10 Research journal & experiment registry

**Research journal** (one markdown file per hypothesis, in `research/journal/H-YYYYMMDD-nn.md`): the §9.1 template up top, then a dated log of every run, decision, and result — *including the failures and why you killed them*. The journal is how you avoid re-testing dead ideas and how you honestly count trials.

**Experiment registry** (`catalog.duckdb`, table `experiments`): one row per run — `run_id`, `hypothesis_id`, `strategy`, `params` (json), `data_version`, `code_git_sha`, `seed`, `date_range`, split, metrics (Sharpe/DSR/PBO/maxDD/turnover/trades), cost assumptions, `passed_kill_check` (bool), `notes`. This makes trial-counting automatic and results queryable.

## 9.11 Reproducibility rules

1. Every run records **code git SHA + config hash + data version + RNG seed**.
2. Same inputs → identical outputs (deterministic core; no wall-clock or unseeded randomness in the decision path).
3. Backtests consume **frozen replay bundles** ([`08`](08-data-strategy.md) §8.5), not live pulls.
4. A run is only "real" if it's in the registry with its provenance; ad-hoc notebook runs don't count toward conclusions.
5. **Backtest↔paper parity test** in CI: replaying a paper session's recorded data through the backtester must reproduce the same decisions.

> **Mindset:** treat every promising backtest as guilty until proven innocent. The controls above are cheap; a real-money loss from a fooled backtest is not. See failure-mode context in [`21-red-team-review.md`](21-red-team-review.md).
