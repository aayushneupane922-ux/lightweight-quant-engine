"""The Narrator (docs/02 §2.6, docs/11 §11.2): the orchestrator's optional
reasoning + explanation layer. It proposes *which ranges to explore* and
narrates what happened — it never optimizes numerically (Optuna does) and
never judges (the gate does).

Two implementations:
- `RuleBasedNarrator` — the default. Deterministic, no LLM: it proposes
  nothing (the model's vetted default space is used) and narrates from a
  template. The whole loop runs on this alone.
- `OllamaNarrator` — optional. Talks to a *local* Ollama server over the
  loopback HTTP API using only the stdlib (no new dependency, no outbound
  network beyond localhost). It emits structured tool calls, which are
  parsed fail-closed (`tools.parse_tool_calls`) and bounded to safe
  refinements (`optimizer.safe_search_space`). On any failure — server
  down, timeout, malformed output — it falls back to the rule-based path,
  so the system loses cleverness, never function (docs/02 §2.6).

Every LLM exchange is captured as an `LlmCallRecord` (prompt, response,
model, temperature, seed) so the orchestrator can log it and a session
replays from the record instead of re-invoking the stochastic model
(docs/11 §11.8).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from lqe.autonomy.tools import Narrate, ProposeSpace, parse_tool_calls

_FROZEN = ConfigDict(frozen=True)


@dataclass(frozen=True)
class HypothesisContext:
    model_id: str
    family: str
    default_ranges: dict[str, tuple[float, float]]
    degraded: bool
    drift_reasons: tuple[str, ...]
    step: int


@dataclass(frozen=True)
class OutcomeContext:
    model_id: str
    degraded: bool
    verdict: Literal["PASS", "FAIL"]
    promoted: bool
    dsr: float
    pbo: float
    fail_reasons: tuple[str, ...]


class LlmCallRecord(BaseModel):
    model_config = _FROZEN
    purpose: str  # "propose_space" | "narrate"
    model: str
    temperature: float
    seed: int
    prompt: str
    response: str
    accepted_tools: list[str]
    rejected: int


@runtime_checkable
class Narrator(Protocol):
    name: str

    def propose_ranges(self, ctx: HypothesisContext) -> dict[str, list[float]]:
        """Proposed `{param: [lo, hi]}` refinements — empty means "use the
        model's default space". The orchestrator clamps these to safe
        bounds regardless (`optimizer.safe_search_space`)."""
        ...

    def narrate(self, ctx: OutcomeContext) -> str: ...

    def drain_calls(self) -> list[LlmCallRecord]:
        """Return and clear the LLM exchanges made since the last drain, for
        the orchestrator to audit. Empty for the rule-based narrator."""
        ...


def _template_narration(ctx: OutcomeContext) -> str:
    prefix = (
        f"{ctx.model_id} degraded on the tracked book; de-risked and re-validated. "
        if ctx.degraded
        else f"Explored {ctx.model_id}. "
    )
    if ctx.promoted:
        body = (
            f"Candidate PASSED the gate (dsr={ctx.dsr:.2f}, pbo={ctx.pbo:.2f}) "
            "and was promoted to the tracked book."
        )
    else:
        why = ", ".join(ctx.fail_reasons) or "n/a"
        body = f"Candidate FAILED the gate — not promoted. Reasons: {why}."
    return prefix + body


@dataclass
class RuleBasedNarrator:
    name: str = "rule_based"

    def propose_ranges(self, ctx: HypothesisContext) -> dict[str, list[float]]:
        return {}  # no LLM smarts -> the vetted default space is used as-is

    def narrate(self, ctx: OutcomeContext) -> str:
        return _template_narration(ctx)

    def drain_calls(self) -> list[LlmCallRecord]:
        return []


@dataclass
class OllamaNarrator:
    """Optional local-LLM narrator. `base_url` is loopback-only by default."""

    model: str = "llama3.1"
    base_url: str = "http://127.0.0.1:11434"
    temperature: float = 0.1  # low temperature for a control loop (docs/07 §7.3)
    seed: int = 0
    timeout_s: float = 20.0
    fallback: RuleBasedNarrator = field(default_factory=RuleBasedNarrator)
    name: str = "ollama"
    _calls: list[LlmCallRecord] = field(default_factory=list)

    def propose_ranges(self, ctx: HypothesisContext) -> dict[str, list[float]]:
        ranges_desc = ", ".join(
            f"{k}: [{lo:g}, {hi:g}]" for k, (lo, hi) in ctx.default_ranges.items()
        )
        degraded_note = (
            f"It just degraded ({', '.join(ctx.drift_reasons)}). " if ctx.degraded else ""
        )
        prompt = (
            "You are a quant research orchestrator. Propose a NARROWER search range "
            f"within these vetted defaults for model '{ctx.model_id}' ({ctx.family}): "
            f"{ranges_desc}. {degraded_note}"
            "Respond ONLY with a JSON array containing one propose_space tool call, e.g. "
            '[{"tool":"propose_space","model_id":"' + ctx.model_id
            + '","ranges":{"<param>":[lo,hi]},"rationale":"..."}]'
        )
        try:
            response = self._chat(prompt)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return self.fallback.propose_ranges(ctx)

        result = parse_tool_calls(response)
        self._calls.append(
            LlmCallRecord(
                purpose="propose_space", model=self.model, temperature=self.temperature,
                seed=self.seed, prompt=prompt, response=response,
                accepted_tools=[c.tool for c in result.calls], rejected=result.rejected,
            )
        )
        for call in result.calls:
            if isinstance(call, ProposeSpace) and call.model_id == ctx.model_id:
                return call.ranges
        return {}  # no usable proposal -> default space (safe)

    def narrate(self, ctx: OutcomeContext) -> str:
        prompt = (
            "Summarize this autonomy step for a research log in one or two sentences. "
            f"model={ctx.model_id}, degraded={ctx.degraded}, verdict={ctx.verdict}, "
            f"promoted={ctx.promoted}, dsr={ctx.dsr:.2f}, pbo={ctx.pbo:.2f}. "
            'Respond ONLY with a JSON array: [{"tool":"narrate","text":"...","refs":[]}]'
        )
        try:
            response = self._chat(prompt)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return self.fallback.narrate(ctx)

        result = parse_tool_calls(response)
        self._calls.append(
            LlmCallRecord(
                purpose="narrate", model=self.model, temperature=self.temperature,
                seed=self.seed, prompt=prompt, response=response,
                accepted_tools=[c.tool for c in result.calls], rejected=result.rejected,
            )
        )
        for call in result.calls:
            if isinstance(call, Narrate) and call.text.strip():
                return call.text.strip()
        return self.fallback.narrate(ctx)  # unusable output -> templated

    def drain_calls(self) -> list[LlmCallRecord]:
        drained = list(self._calls)
        self._calls.clear()
        return drained

    def _chat(self, prompt: str) -> str:
        """POST to the local Ollama chat API using only the stdlib. Raises on
        any transport/parse failure so callers fall back cleanly."""
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": self.temperature, "seed": self.seed},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat", data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as resp:  # noqa: S310 - loopback only
            body = json.loads(resp.read().decode("utf-8"))
        content = body.get("message", {}).get("content", "")
        if not isinstance(content, str):
            raise ValueError("unexpected Ollama response shape")
        return content


def make_narrator(*, use_llm: bool = False, model: str = "llama3.1", seed: int = 0) -> Narrator:
    """Factory: the rule-based narrator by default; an Ollama-backed one when
    `use_llm` is set (which still falls back to rule-based if the server is
    absent). The system is fully functional either way."""
    if use_llm:
        return OllamaNarrator(model=model, seed=seed)
    return RuleBasedNarrator()
