"""Narrator behaviour (docs/02 §2.6): the rule-based narrator is
deterministic and self-sufficient; the Ollama narrator degrades gracefully
when the server is absent; LLM range proposals are clamped to safe
refinements of the vetted defaults.
"""

from __future__ import annotations

from lqe.autonomy.narrator import (
    HypothesisContext,
    OllamaNarrator,
    OutcomeContext,
    RuleBasedNarrator,
    make_narrator,
)
from lqe.autonomy.optimizer import ParamRange, SearchSpace, safe_search_space

_HYP = HypothesisContext(
    model_id="trend_ma_cross", family="trend",
    default_ranges={"fast": (2.0, 20.0), "slow": (21.0, 80.0)},
    degraded=False, drift_reasons=(), step=1,
)
_OUT_FAIL = OutcomeContext(
    model_id="trend_ma_cross", degraded=False, verdict="FAIL", promoted=False,
    dsr=0.3, pbo=0.7, fail_reasons=("dsr low",),
)


def test_factory_defaults_to_rule_based() -> None:
    assert make_narrator().name == "rule_based"
    assert make_narrator(use_llm=True).name == "ollama"


def test_rule_based_proposes_nothing_and_narrates_deterministically() -> None:
    n = RuleBasedNarrator()
    assert n.propose_ranges(_HYP) == {}
    assert n.drain_calls() == []
    assert n.narrate(_OUT_FAIL) == RuleBasedNarrator().narrate(_OUT_FAIL)  # deterministic
    assert "FAILED" in n.narrate(_OUT_FAIL)


def test_ollama_narrator_falls_back_when_server_absent() -> None:
    # nothing is listening on this port -> connection refused -> graceful fallback
    n = OllamaNarrator(base_url="http://127.0.0.1:1", timeout_s=0.5)
    assert n.propose_ranges(_HYP) == {}  # -> use default space
    narration = n.narrate(_OUT_FAIL)
    assert "FAILED" in narration  # templated fallback
    # the failed calls never got as far as logging a response
    assert n.drain_calls() == []


def test_safe_search_space_clamps_llm_proposals_inside_vetted_bounds() -> None:
    default = SearchSpace(
        model_id="trend_ma_cross",
        ranges={
            "fast": ParamRange(low=2, high=20, is_int=True),
            "slow": ParamRange(low=21, high=80, is_int=True),
        },
    )
    # fast is a valid narrowing; slow is absurd/out-of-bounds -> clamped to default
    proposal: dict[str, list[float]] = {"fast": [5.0, 10.0], "slow": [10.0, 9999.0]}
    merged = safe_search_space(default, proposal)
    assert (merged.ranges["fast"].low, merged.ranges["fast"].high) == (5.0, 10.0)
    assert (merged.ranges["slow"].low, merged.ranges["slow"].high) == (21.0, 80.0)


def test_safe_search_space_ignores_malformed_or_widening_proposals() -> None:
    default = SearchSpace(
        model_id="m", ranges={"x": ParamRange(low=10, high=20, is_int=True)}
    )
    bads: list[dict[str, list[float]]] = [
        {"x": [5.0, 100.0]}, {"x": [1.0]}, {"x": []}, {"x": [20.0, 20.0]}, {}
    ]
    for bad in bads:
        merged = safe_search_space(default, bad)
        lo, hi = merged.ranges["x"].low, merged.ranges["x"].high
        assert 10.0 <= lo < hi <= 20.0  # never escapes the vetted bounds
