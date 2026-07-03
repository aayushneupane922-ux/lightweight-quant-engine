# 21 — Red-Team Review

I now argue *against* my own recommendations. Each attack is steelmanned, then I give a verdict: does it change the plan? The goal is to surface where I might be wrong before you commit.

## Attack 1 — "Building a custom engine is the classic beginner mistake."
**Steelman:** Every quant forum is full of people who spent a year building a backtester and never traded. LEAN/Nautilus exist precisely so you don't reproduce look-ahead bugs, fill optimism, and accounting drift. You'll rebuild — badly — what teams of engineers already got right.
**Rebuttal:** Valid and the strongest attack. Two things blunt it: (1) the custom scope here is *small and bounded* (~3k lines) because the heavy lifting (data, indicators, analytics, portfolio math) is delegated to libraries — you're building plumbing, not a framework; (2) your non-negotiables (provable live-lockout, risk-gate-on-every-order, deterministic replay) are *harder* to guarantee inside someone else's engine than to write yourself. **Verdict: plan stands, but the risk is real** — mitigation is the test plan ([`16`](16-mvp-build-plan.md) §16.12) and the research protocol ([`09`](09-backtesting-research-protocol.md)) that catch exactly the bugs this attack predicts. If you find yourself building a *framework* rather than an *app*, stop and reconsider Nautilus.

## Attack 2 — "You should just use Nautilus now and skip the rewrite later."
**Steelman:** If Nautilus is the long-term engine, adopting it now avoids a migration and gives you determinism + live-readiness for free.
**Rebuttal:** The migration is cheap *because* the interfaces are identical (D1/D13) — you're not throwing away strategies, data, or research. Adopting Nautilus now imposes its full learning curve and LGPL considerations *before* you've validated a single strategy, which is premature optimization for power you don't yet need. **Verdict: plan stands** — but if you *already* know Rust/Nautilus or expect live trading within months, jumping straight to Nautilus is defensible.

## Attack 3 — "Crypto-first is a data-quality and regime trap."
**Steelman:** Crypto has manipulated volume, exchange outages, wash trading, depegs, and non-stationary regimes. A strategy validated on crypto may be validated on noise. Free crypto data may be dirtier than you think.
**Rebuttal:** True — which is why data-quality checks and cross-exchange validation are a *Milestone 2* first-class feature, not an afterthought ([`08`](08-data-strategy.md)). Crypto-first is chosen for **$0 real-time data availability to exercise the engine**, not because crypto is a clean market. The engine and discipline are the deliverable; the market is swappable via adapters. **Verdict: plan stands, with eyes open** — treat crypto results as engineering validation, not a profitability claim (which we make none of anyway).

## Attack 4 — "Paper trading gives false confidence; it's not real."
**Steelman:** Paper omits queue position, impact, latency, and fills in fast markets. Graduating from paper tells you little about live.
**Rebuttal:** Agreed, and stated explicitly ([`14`](14-safety-risk-and-compliance-review.md) §14.2): *paper is an optimistic upper bound.* Its value in the MVP is not "predicting live P&L" — it's (a) exercising the full event/risk/audit machinery in real time, (b) catching backtest↔reality divergences in decisions (parity), and (c) building operational discipline. Live is out of scope precisely because paper≠live. **Verdict: plan stands** — paper's role is correctly scoped as engineering, not proof of edge.

## Attack 5 — "NiceGUI is niche; Streamlit has a bigger community."
**Steelman:** Streamlit has more resources, examples, and Claude Code training data; NiceGUI is newer with a smaller community.
**Rebuttal:** For a *stateful, live-updating* trading monitor, Streamlit's rerun-the-script model is a genuine mismatch; NiceGUI's WebSocket/event model fits ([`13`](13-lightweight-ui-spec.md)). We keep Streamlit for research reports where it shines. **Verdict: plan stands** — but if you struggle with NiceGUI, a Streamlit research UI + a minimal Textual/CLI monitor is an acceptable fallback. This is the lowest-stakes decision in the package.

## Attack 6 — "$0 is a false economy; you'll waste time babysitting free data."
**Steelman:** Cleaning free data and working around rate limits costs more (in your time) than a $50/mo feed.
**Rebuttal:** Partly true, and flagged ([`07`](07-free-and-low-cost-plan.md) §7.5: the real cost of $0 is your time). But in the *research/paper* phase, building the data-validation muscle is valuable *regardless* of source, and crypto public data is genuinely sufficient to exercise everything. **Verdict: plan stands for MVP** — with an explicit trigger to pay once a strategy graduates (D4). Don't cheap out on data when real decisions depend on it.

## Attack 7 — "10 milestones is too much; you'll never finish."
**Steelman:** Solo projects die from scope. Ten milestones + a research protocol + a UI is a lot; motivation fades before Milestone 8.
**Rebuttal:** Real risk. Mitigation: the milestones are ordered so you have a *usable* system early — after M3 you can backtest, after M6 you can see results, after M8 you can paper-trade. Each milestone is independently valuable and ends in a review checkpoint. **Verdict: plan stands, but consider a "thin slice" MVP** — M1→M3→M6 (core → backtest → minimal UI) as a first release, deferring M7–M10. This is the single best de-risking move if time is tight.

## Attack 8 — "The research discipline is so strict you'll kill every strategy and quit."
**Steelman:** DSR/PBO/walk-forward will reject almost everything; a discouraged solo dev may abandon the project or, worse, quietly relax the criteria.
**Rebuttal:** Killing most strategies *is the correct outcome* ([`09`](09-backtesting-research-protocol.md) §9.9) — the alternative is trading curve-fits. The motivational risk is real; the mitigation is that the *engine and process* are the deliverable, and finding one strategy that survives honest scrutiny is worth more than a hundred that don't. **Verdict: plan stands** — but budget emotionally for a high kill rate; it's success, not failure.

## Attack 9 — "You under-weighted the possibility that Claude Code reproduces subtle look-ahead bugs."
**Steelman:** An LLM building a backtester may introduce off-by-one bar-timing or fill look-ahead that passes naive tests but inflates results.
**Rebuttal:** This is the most insidious risk and I take it seriously. Mitigations: explicit bar-completeness rule + tests ([`08`](08-data-strategy.md) §8.2, [`18`](18-claude-code-milestone-prompts.md) M3), pessimistic fills, cost-sensitivity sweeps, random-entry controls, and backtest↔paper parity. **Verdict: plan stands, and this is why the protocol exists** — but you should personally spot-check the bar-timing and fill logic, not just trust green tests.

## Attack 10 — "The whole thing assumes you'll trade discretionarily via Sierra eventually; this may be the wrong foundation."
**Steelman:** Your skills/context hint at discretionary futures trading via Sierra. A crypto Python engine may not transfer.
**Rebuttal:** The engine, risk gate, audit, and research discipline transfer to *any* market via adapters; only the data/execution edges change. Sierra is explicitly a *later, separate* track ([`14`](14-safety-risk-and-compliance-review.md), D14). **Verdict: plan stands** — the asset-agnostic core is the hedge against exactly this uncertainty.

## Net assessment

The plan survives red-teaming, with three honest caveats you should internalize:
1. **Custom-engine risk is real** (Attack 1) — mitigated by small scope + tests, but stay vigilant against framework-building.
2. **Consider a thin-slice release** (Attack 7) — M1→M3→M6 first if time/motivation is constrained.
3. **Budget for a high strategy kill-rate** (Attack 8) and personally audit bar-timing/fills (Attack 9).

None of these change the core recommendation. All are captured as risks in [`22`](22-unanswered-questions.md).
