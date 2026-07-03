# 03 — Model Catalog (FINAL)

Host a large, extensible library of **advanced statistical + proven quant models** — scaled via adapters, not hand-written one by one — with discipline that grows with the catalog. Consolidates the archived catalog specs; sourcing map: [awesome-quant](https://github.com/wilsonfreitas/awesome-quant).

## 3.1 Principle: breadth by adapter, safety by gate
- **One adapter unlocks a whole family** through config (highest leverage for "as many models as possible").
- Every model is **deterministic, permissively licensed, manifest-complete, and validatable** — else it's quarantined (transparently).
- Size is a *research surface*; the promotion gate ([`04`](04-validation-and-overfitting-protocol.md)) and trial-counting are what keep a big catalog honest.

## 3.2 Families & sources (all permissive)
| Family | Example models | Library (license) |
|---|---|---|
| Trend / breakout | MA/MACD cross, Donchian, ADX-gated | pandas-ta (MIT), own |
| Momentum | time-series momentum, dual-momentum | own + pandas |
| Mean-reversion | z-score, Bollinger, RSI fade | pandas-ta (MIT) |
| Pairs / stat-arb | cointegration spread, VECM | statsmodels (BSD-3) |
| Volatility | GARCH/EGARCH filters, vol-target | arch (NCSA) |
| Regime | HMM, change-point, Markov-switching | hmmlearn (BSD), ruptures (BSD-2) |
| Portfolio | MVO, Black-Litterman, HRP, CLA | PyPortfolioOpt (MIT), skfolio (BSD-3) |
| Risk allocation | risk parity, HERC, 20+ risk measures | riskfolio-lib (BSD-3) |
| Supervised ML signals | logistic/RF/gradient-boosting, meta-labeling | scikit-learn (BSD), LightGBM (MIT) |
| Online / drift | incremental baselines, ADWIN/DDM | River (BSD-3) |

Advanced statistical models (ADF/Johansen cointegration, GARCH-family, HMM/Markov-switching regimes, Kalman filters via statsmodels, Bayesian shrinkage in skfolio) are first-class, not afterthoughts — they're the "advanced statistical" half you asked for.

**Excluded** (integrity/scope): Backtrader (GPL/unmaintained), vectorbt-as-engine (Commons Clause). RL frameworks (FinRL/TensorTrade) may be *observed* as sandbox models but never given autonomous authority (nondeterministic; docs [`archive/15`](archive/15-open-source-license-review.md)).

## 3.3 Plugin contract (add a model = one small unit)
Each model = `implementation + manifest + tests`. The manifest is the single source the UI/catalog renders:
```yaml
id: donchian_breakout
family: trend
one_liner: "Enter when price clears the N-bar channel."
economic_rationale: "Breakouts can extend when order flow is one-sided."
data_needs: {instruments: 1, kind: OHLCV}
oss_libs: ["pandas-ta"]
params_schema: {lookback: int>1, stop_atr: float>0}   # the space Optuna searches
failure_modes: ["false breakouts in range regimes"]
validation: {min_trades: 200, needs: [walk_forward, dsr, cost_sweep]}
status: unproven    # set to 'validated' ONLY by a passing gate run, never by an author or the LLM
deterministic: true
```
Two kinds: **native plugins** (written to the `Strategy`/`Model` interface) and **library-adapter plugins** (`PandasTaRuleAdapter`, `SkfolioOptimizerAdapter`, `PyPortfolioOptAdapter`, `RiskfolioAdapter`, `StatsmodelsPairsAdapter`, `ArchVolAdapter`) that expose many configurable models each. Adapters are how the catalog reaches 50+ without 50 files.

## 3.4 Intake (curation, not dumping)
A candidate lists only after passing: license check (permissive), determinism check, `SignalEvent`-only (no order construction, no network in decision path), manifest complete, tests + a completing Research backtest. Fails → transparent **quarantine list** with the reason. Enters as `status: unproven`; observable/searchable but **cannot be promoted or ranked "validated"** until it passes the gate.

## 3.5 Organization at scale (50+ models stay usable)
Browse by family with filters (data-needs, status, license, timeframe); search + `⌘K` palette; adapter presets + a params editor; a "compare/add-to-floor" tray. The autonomy loop treats the catalog as its **search space** — the LLM picks which models/params to explore; Optuna searches within each model's `params_schema`.

## 3.6 Honesty at scale (mandatory)
- Trial-counting spans the **whole catalog**: the DSR/PBO gate uses the full count of models × params tried, so a big catalog can't smuggle in a lucky winner.
- Include ≥1 **deliberately weak model** (e.g., naive MVO) so the tooling visibly rejects things.
- Every catalog performance number carries sample size + cost + `unproven/validated` status (see UI honesty rules, [`05`](05-ui-and-3d-visualization.md)).

## 3.7 Acceptance criteria
- Adding a model = one folder passing intake; adapters unlock families by config; catalog scales to 50+ without per-model bloat.
- Advanced statistical models (cointegration, GARCH, HMM, Bayesian allocation) present as first-class.
- Every listed model deterministic + permissive + manifest-complete + `unproven` until gated; quarantine transparent; runtime license gate green.
