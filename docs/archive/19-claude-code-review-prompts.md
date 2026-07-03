# 19 — Claude Code Review Prompts

Run these **between milestones** and before any merge touching `risk/`, `execution/`, or `paper/`. They are adversarial on purpose — the reviewer's job is to *break* the safety and honesty guarantees, not to praise the code.

---

## 19.1 Safety / live-lockout review (run after every milestone; mandatory for risk/execution/paper changes)

```
Act as a trading-systems safety reviewer with veto power. Audit the current codebase and
PROVE (or disprove) each claim. For any FAIL, stop and fix before proceeding.

1. LIVE LOCKOUT
   - Grep the entire repo: is there ANY code path that could place a real order?
     (broker SDK imports, ccxt create_order/cancel_order/withdraw, http POST to an
     exchange trading endpoint, anything named live/real/prod execution). List findings.
   - Is `LIVE_TRADING_ENABLED` False and impossible to flip via config/env in MVP?
   - Does startup assert execution_adapter.is_paper is True and refuse to run otherwise?
   - Does the config schema REJECT mode: live and non-paper execution adapters? Show the test.
   - Is PaperBroker the ONLY class implementing ExecutionAdapter? Prove via test.

2. RISK GATE
   - Is there exactly ONE function that constructs Order, and does it call RiskEngine.check first?
   - Can any code emit an Order without an APPROVE/CLAMP decision? Try to construct a bypass.
   - Do risk rules fail CLOSED on bad/missing config/state?

3. KILL SWITCH
   - Once kill_active is set, can any risk-increasing order be emitted? Prove not.
   - Does kill persist across restart and never auto-clear?

4. DETERMINISM / AUDIT
   - Do two identical runs produce identical audit hashes? Run it.
   - Does the audit hash-chain verify? Is the log append-only?

Output a PASS/FAIL table for every item with evidence (file:line, test name, or command
output). Do not mark PASS without evidence.
```

---

## 19.2 Code-quality / architecture review

```
Act as a senior architect reviewing for a SOLO maintainer. Check:
- Module boundaries respected (docs/16 §16.3): no third-party type leaks past its adapter;
  core depends on nothing project-specific; ui never imports risk/execution internals.
- Interfaces match docs/12 contracts. Any drift?
- Complexity budget: is the core still small enough to read in an afternoon? Flag any
  module that's growing framework-like or clever. Prefer boring.
- Types: mypy clean, no `Any` in core/risk/execution. Ruff clean.
- Determinism smells: wall-clock reads outside Clock, unseeded RNG, dict-order reliance,
  network/IO in the decision path. List every instance.
- Dead code / scope creep: anything from docs/16 §16.7 "what NOT to build" sneaking in?
Output prioritized findings (blocker / should-fix / nit) with file:line.
```

---

## 19.3 Research-methodology review (run when strategy/analytics code changes)

```
Act as a quant research methodologist enforcing docs/09. For the strategy/analytics in
this change:
- Is there a written economic rationale + falsifiable failure prediction (research journal)?
- Are train/validation/test splits fixed by date and is the test set touched at most once?
- Is the signal causal (acts only on completed bars, no future data)? Show the guard.
- Is the cost-sensitivity sweep present, and does the edge survive realistic bps?
- Is the trial count logged, and is a Deflated Sharpe / PBO reported for the honest N?
- Is there a random-entry / equal-weight / buy-and-hold benchmark comparison?
- Does the result look like a parameter PLATEAU or a SPIKE? Show the sensitivity map.
- Run the docs/09 §9.9 "kill the strategy if..." checklist and report each item.
Conclude: does this strategy meet the graduation criteria (docs/09 §9.8)? If not, say
exactly which criteria fail. Default to "not yet."
```

---

## 19.4 Data-quality review (run when data code changes)

```
Act as a data-quality auditor enforcing docs/08 §8.4. Verify each check exists and fires:
monotonic/unique timestamps, OHLC sanity, volume, gap report, outliers, checksum+manifest,
canonical symbol mapping, survivorship (delisted kept). Inject a failure for each and show
it is caught and quarantined (not silently fixed). Confirm all timestamps are UTC left-edge
and that gaps produce "no trade", never a guessed fill. Output a PASS/FAIL table.
```

---

## 19.5 License review (run when dependencies change)

```
Act as a license auditor enforcing docs/15. Run pip-licenses (or equivalent) on the RUNTIME
dependency tree. FAIL if any runtime dep is GPL or carries Commons Clause. Confirm vectorbt
(if present at all) is not imported by src/lqe/** (research-only). Confirm Backtrader is
absent. Regenerate THIRD_PARTY_NOTICES. Output the offending packages (if any) and the fix.
```

---

## 19.6 Pre-merge gate (the one-line checklist the agent must satisfy)

```
Before merging: ruff clean, mypy clean, ALL tests green (unit+property+parity+safety+data),
safety review 19.1 all PASS with evidence, audit hash-chain verifies, license gate green,
docs updated, and nothing from docs/16 §16.7 was added. If any item is red, do not merge —
report it and stop.
```

> **Rule of thumb for the reviewer:** absence of evidence is a FAIL, not a PASS. "I couldn't find a live path" is not the same as "I proved no live path exists." Demand the proving test.
