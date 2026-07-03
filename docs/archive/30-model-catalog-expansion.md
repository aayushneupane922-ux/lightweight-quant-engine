# 30 — Model Catalog Expansion ("Host as Many OSS Models as Possible")

Non-negotiable #3: the Showcase should host as much of the open-source quant-model universe as possible. This file makes that a **scalable architecture + a sourcing pipeline + a safety filter** — not a hardcoded list. It extends docs/25.

## 30.1 The reframing that makes "all of them" sane
You can't (and shouldn't) hand-port every OSS model. Instead:
- **Standardize a plugin contract** so adding a model is a small, repeatable unit of work.
- **Wrap external libraries behind adapters** so one adapter unlocks *many* models at once.
- **Curate, don't dump.** A model only enters the catalog if it's **deterministic, testable, permissively licensed, and honestly validatable** (docs/09). Quantity is a feature only if every entry meets the bar; a catalog full of un-validatable black boxes is worse than a small honest one.

## 30.2 Sourcing map — where the models come from
Primary index: **awesome-quant** (wilsonfreitas) — the canonical curated list of OSS quant libraries; mine it systematically. ([awesome-quant](https://github.com/wilsonfreitas/awesome-quant)) Buckets to harvest, mapped to the four families (docs/25):

| Source (permissive) | Models it unlocks | Family | License |
|---|---|---|---|
| pandas-ta / TA-Lib | 130+ indicators → dozens of rule strategies | trend/mean-rev/breakout | MIT/BSD |
| own implementations | Donchian, TS-momentum, z-score, RSI, channel | trend/mean-rev | yours |
| statsmodels | cointegration/pairs, VECM | pairs/stat-arb | BSD-3 |
| arch | GARCH-family vol models/filters | volatility | NCSA |
| hmmlearn / ruptures | regime detectors → regime-gated strategies | regime | BSD |
| PyPortfolioOpt | MVO, Black-Litterman, HRP, CLA | portfolio | MIT |
| skfolio | 20+ estimators/optimizers, HRP/NCO, risk measures | portfolio | BSD-3 |
| riskfolio-lib | risk parity, HERC, 20+ risk measures | portfolio | BSD-3 |
| scikit-learn / LightGBM | supervised signal models (later, gated) | ML factor | BSD/MIT |

Deliberately **excluded from the catalog** (safety/scope): Backtrader (GPL, unmaintained), vectorbt-as-engine (Commons Clause), FinRL/TensorTrade **as autonomous traders** (RL violates deterministic/no-autonomy constraints — may appear later only as *observed, gated* research, never auto-trading). See docs/15.

## 30.3 The plugin contract (add a model in one small unit)
Every catalog model is a folder: `implementation + manifest + tests`. The manifest (docs/25 §25.1) is the single source of truth the Showcase renders. Two plugin kinds:

- **Native plugin:** a `Strategy`/`Model` written against the engine interfaces (deterministic, `SignalEvent`-only).
- **Library-adapter plugin:** wraps an external lib's model behind the same interface. One adapter (e.g. `SkfolioOptimizerAdapter`, `PyPortfolioOptAdapter`, `PandasTaRuleAdapter`) exposes *many* configurable models via params — the highest-leverage way to "host many."

```python
# a library-adapter unlocks a whole family through config, not N files
class PandasTaRuleAdapter(Strategy):
    """Turns any pandas-ta indicator + a comparison rule into a deterministic strategy."""
    # manifest lists the concrete presets (e.g., 'ema_cross', 'rsi_reversion', 'macd_trend')
```

## 30.4 The intake pipeline (curation, not dumping)
Each candidate model passes an **intake checklist** before it's listed:
1. **License** MIT/BSD/Apache/NCSA (license gate) — else rejected.
2. **Deterministic** + `SignalEvent`-only + no network/credentials in the decision path.
3. **Manifest complete:** family, economic rationale, data needs, failure modes, params schema.
4. **Tests:** unit + a Research backtest that runs to completion with cost modeling.
5. **Status = `unproven`** on entry (never author-set to validated).
6. Registered in the catalog index; appears in Showcase (observable) but **cannot be ranked/validated** until it passes a Research graduation run (docs/09 §9.8).

A model that can't clear intake goes to a **quarantine list** with the reason (visible in an "unsupported" view), so the boundary is transparent.

## 30.5 Catalog scale & organization (so 50+ models stay usable)
- **Browse by family** (docs/25) with filters: data-needs (1 vs basket vs universe), wave, status, license, timeframe.
- **Search + command palette** (`⌘K`) to jump to any model.
- **Presets vs. custom:** adapters ship curated presets (sane defaults) *and* a params editor for power users.
- **"Compare" tray:** select up to N models → send to a Race (docs/26) or a Research comparison.
- Target: **Wave A ships ~10–15** concrete models (enough for a real "10 models racing" floor); the adapter approach then scales to **50+** across waves B/C without 50 hand-written files.

## 30.6 Honesty at scale
More models = more multiple-testing = more overfitting risk. So:
- The Intelligence/leaderboard honesty layer (docs/26 §26.4, docs/29) is **mandatory** regardless of catalog size.
- Trial-counting (docs/09) spans the *whole catalog*: testing 50 models on the same data inflates the best one's apparent Sharpe — the DSR/PBO must reflect the full count.
- Include ≥1 **deliberately weak model** so users routinely see the tooling reject something. A big catalog is a bigger overfitting trap; the discipline is what makes it safe.

## 30.7 Acceptance criteria
- Adding a model = one folder (impl + manifest + tests) passing intake; library-adapters unlock families via config.
- Wave A lists ≥10 models across the four families for a real racing floor; architecture scales to 50+ without per-model bloat.
- Every listed model is deterministic, permissive, manifest-complete, `unproven` until graduated; quarantine list is transparent.
- License gate green across the expanded dependency set; runtime stays permissive (heavy ML libs in `research` extra).
