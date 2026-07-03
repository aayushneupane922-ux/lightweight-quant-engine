# GUARDRAILS — Read Before Adding Anything New

The boundary fence for this project. If you (agent or human) are about to build something, add a dependency, or feel the urge to expand scope — read this first. It exists to stop drift.

## NEVER (hard stops — a test should fail if any is violated)
- ❌ Place, or make it possible to place, a **real order**. No broker SDK, no credentials, no `ccxt` order/withdraw calls anywhere. `PaperBroker` (`is_paper=True`) is the only `ExecutionAdapter`.
- ❌ Add a `live`/real execution mode. `LIVE_TRADING_ENABLED=False` with no supported flip; config Enums exclude it.
- ❌ Construct an `Order` anywhere except the single `make_order(intent, decision)` choke point, and only after a non-REJECT risk decision.
- ❌ Let the **LLM** optimize numerically, set `validated`, size/place orders, bypass the promotion gate, or disable the kill switch. LLM emits only the 5 structured tool-calls (`docs/11` §11.6).
- ❌ Promote anything to the TRACKED book that hasn't passed the `Validator`/`PromotionGate` (walk-forward + DSR + PBO + cost + beats equal-weight/random).
- ❌ Change the live/tracked book to chase recent performance. Degradation → **de-risk + re-validate on history**, never live-curve-chasing.
- ❌ Render raw CLI/stdout in the GUI. Structured components only.
- ❌ Expose a port / add `--host` / add auth. `127.0.0.1` only.
- ❌ Add a runtime dependency under a **DENY** license: GPL, AGPL, SSPL, BSL/Business Source, or Commons Clause. **ALLOW** = MIT, BSD, Apache-2.0, ISC, PSF, NCSA, 0BSD, Unlicense, **MPL-2.0** (weak file-level copyleft — fine as an *unmodified* dep, e.g. `certifi`); LGPL is allowed for an unmodified/dynamically-imported dep (flag if you freeze a binary). The license CI gate must scan the **full runtime transitive tree** and **fail closed** on any unknown license. `vectorbt` (if ever) is offline-research only; never import Backtrader (GPL). Full policy: `docs/11` §11.11.
- ❌ Make any claim of profitability in code, UI, comments, or docs.
- ❌ Introduce nondeterminism into a sim result (unseeded RNG, wall-clock reads outside `Clock`, network/IO in a decision path, dict-order reliance).

## OUT OF SCOPE — do NOT build (even if it seems helpful)
- Live trading, real broker adapters, credentials, order routing.
- Sierra Chart / DTC anything (generic adapter seams only).
- Cloud deploy, multi-user, remote UI, accounts/auth.
- RL as an autonomous trader; LLM-as-numerical-optimizer; deep learning in the decision loop.
- Options, order-book/L2 microstructure, HFT.
- An "equity always up / minimize drawdown" objective function.
- Any model that isn't deterministic + permissively licensed + manifest-complete.
- Features not traceable to a `docs/` spec. If it's not in the docs, it's not in scope — propose it, don't build it.

## STOP and ask the human when…
- A request or idea conflicts with any NEVER above.
- You'd add a new runtime dependency (confirm license first).
- You'd touch a safety gate (`risk/`, `execution/`, `autonomy/promotion_gate`, `kill_switch`, lockout).
- A spec is ambiguous, missing, or two docs disagree.
- You'd deviate from the milestone order in `docs/10` — especially **M8 (autonomy) before M4 (the gate)**.
- You'd expose anything beyond `127.0.0.1`, or handle any credential/secret.
- You're unsure whether something is in scope. Default to asking, not building.

## Scope-creep tells (self-check before writing code)
- "This would be cool if…" → probably out of scope.
- You're building a *framework*, not the *app*. Stop; own a small spine.
- Adding config knobs, abstractions, or models nobody asked for.
- Gold-plating the UI or the 3D view beyond the spec.
- Adding models to "look robust" (breadth ≠ robustness; the gate + trial-counting decide robustness).
- Reaching for the live feed as a training signal (it's a trigger/monitor, not the teacher).

## The prime directive
Exploration is free in the SANDBOX; the LIVE/TRACKED book only accepts gate-validated changes. Paper-only and audit/determinism are hard rails. When in doubt, choose the **smaller, safer, more deterministic, more honest** option — and if still in doubt, **stop and ask**.
