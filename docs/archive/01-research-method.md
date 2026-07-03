# 01 — Research Method

## Purpose

Document *how* this research package was produced so you (and Claude Code) can judge its reliability, reproduce it, and know where the soft spots are.

## Ground rules applied

1. **Facts, assumptions, recommendations, risks, and open questions are separated** throughout. Each deeper file uses explicit headers or inline tags.
2. **Confidence tagging.** Claims are tagged where it matters:
   - `[Certain]` — backed by a primary/official source (license file, vendor pricing page, docs).
   - `[Likely]` — strong inference from multiple credible sources or well-established engineering practice.
   - `[Guessing]` — filling a gap; must be verified before spending money or writing dependent code.
3. **Source hierarchy.** Preference order: official docs / license files / GitHub repos / package registries (PyPI, crates.io) > vendor pricing pages > peer-reviewed or arXiv papers > credible technical writeups > forum posts. Marketing pages are treated as claims, not facts.
4. **No profitability claims.** Any statement about a model or strategy is about *what it is, how to test it, and how it fails* — never whether it makes money.
5. **Cost is never hand-waved.** Every cost line has a free option, a paid option, an estimated range, and a citation or an explicit `[Guessing]` tag.
6. **Data licensing is never hand-waved.** Free data is treated as *possibly unreliable and possibly ToS-restricted* until proven otherwise.

## Scope boundaries (as instructed)

- **In scope:** open-source quant frameworks/libraries/models, architecture options, cost, data strategy, backtesting protocol, paper-trading engine, risk engine, lightweight UI, safety/compliance (non-legal), and a full Claude Code build package.
- **Explicitly out of scope:** deep research into **Sierra Chart, DTC protocol, Sierra settings/message behavior**. Only generic `MarketDataAdapter` / `ExecutionAdapter` seams are designed so Sierra can be researched separately later.
- **De-prioritized (minimal effort, per instruction):** live broker integration, cloud deployment, advanced ML optimization, HFT infrastructure, options-specific complexity, production live trading.

## Decisions treated as "hard" (where reasoning effort was concentrated)

1. **Build vs. adopt** LEAN / NautilusTrader / custom / hybrid — see [`04`](04-architecture-options.md), [`05`](05-recommended-architecture.md).
2. **Which open-source models belong in MVP** vs. later vs. never — see [`03`](03-open-source-model-taxonomy.md).
3. **How to avoid overfitting** (the real failure mode) — see [`09`](09-backtesting-research-protocol.md).
4. **How to design paper trading correctly** and make accidental live trading structurally impossible — see [`10`](10-paper-trading-engine-spec.md), [`11`](11-risk-engine-spec.md).
5. **How to keep the UI lightweight** — see [`13`](13-lightweight-ui-spec.md).
6. **How to keep costs at ~$0** — see [`06`](06-cost-analysis.md), [`07`](07-free-and-low-cost-plan.md).
7. **How to make Claude Code implementation deterministic and safe** — see [`16`](16-mvp-build-plan.md)–[`19`](19-claude-code-review-prompts.md).

## Research process actually followed

1. **Clarified three load-bearing ambiguities** with the user before researching: target market (**crypto-first, asset-agnostic core**), packaging (**local app in a desktop window**), budget (**$0 strict**). These answers shaped every downstream recommendation.
2. **Framework/license sweep** — verified current license, maintenance status, and runtime for each candidate against GitHub/PyPI/official docs (July 2026).
3. **Data + cost sweep** — verified free tiers, rate limits, and pricing for crypto public APIs, Alpaca, and Claude Code.
4. **UI + model-library sweep** — verified NiceGUI/Streamlit/packaging and the specific model libraries (statsmodels/arch/hmmlearn/ruptures/skfolio).
5. **Synthesis** into architecture and cost recommendations.
6. **Red-team** of my own recommendations — see [`21`](21-red-team-review.md).
7. **Revision** then production of the 24 deliverable files.

## Known limitations of this research

- **Knowledge cutoff drift.** Base knowledge is anchored to ~May 2025; this package uses July-2026 web results to correct it, but fast-moving items (pricing tiers, free-data ToS, library releases) can change again. **Re-verify anything cost- or license-sensitive before committing.**
- **US-centric search.** Web search returns US-region results; non-US broker/data availability may differ.
- **No hands-on benchmarking.** Performance/complexity statements are from docs and credible writeups, not from running the frameworks in your environment. Treat them as `[Likely]`, not `[Certain]`.
- **License interpretation is not legal advice.** The license review ([`15`](15-open-source-license-review.md)) is an engineering reading, not a lawyer's opinion. Distribution scenarios (shipping a Windows `.exe`) especially warrant professional review before commercial release.

## Reproducibility

Every claim that matters is linked. To reproduce or refresh: re-run the same category searches (frameworks+license, data+pricing, UI+models, research-discipline) and diff against [`23-appendix-source-map.md`](23-appendix-source-map.md). Timestamp your refresh, because these facts decay.
