"""Marker-gated integration test against a REAL local Ollama server (docs/12
M16). Auto-skips unless a server is actually reachable on 127.0.0.1:11434 --
no CI runner has a local LLM installed, so this is never expected to run
there; it runs automatically on a machine that has Ollama up (this dev
machine -- see HANDOFF.md/COMPONENT-GUIDE.md sec 11), or manually via:

    ollama serve  # if not already running
    pytest -m llm_integration tests/integration/test_ollama_narrator_live.py -v

Every other narrator test in the suite (test_orchestrator_narrator.py etc.)
uses a fake/stubbed transport -- this is the only one that proves the real
HTTP round trip (structured-output `format`, `num_ctx` bound, fail-closed
parsing of genuine model output) actually works end to end, closing the gap
where that was previously verified manually but never automated.
"""

from __future__ import annotations

import socket

import pytest

from lqe.autonomy.narrator import HypothesisContext, OllamaNarrator, OutcomeContext

pytestmark = pytest.mark.llm_integration

_WHITELISTED_TOOLS = {"propose_space", "run_trials", "promote_if_valid", "de_risk", "narrate"}


def _ollama_reachable(host: str = "127.0.0.1", port: int = 11434, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


_REASON = "requires a real local Ollama server on 127.0.0.1:11434 (see HANDOFF.md sec 1a)"


@pytest.mark.skipif(not _ollama_reachable(), reason=_REASON)
def test_narrate_completes_a_genuine_round_trip() -> None:
    narrator = OllamaNarrator(model="llama3.2:3b", num_ctx=4096, timeout_s=45.0)
    ctx = OutcomeContext(
        model_id="macd_trend_0", degraded=False, verdict="PASS", promoted=True,
        dsr=0.8, pbo=0.1, fail_reasons=(),
    )

    text = narrator.narrate(ctx)
    assert isinstance(text, str) and text.strip()

    calls = narrator.drain_calls()
    # exactly one LlmCallRecord proves a real HTTP round trip happened --
    # a connection failure would have fallen back without recording a call.
    assert len(calls) == 1
    record = calls[0]
    assert record.model == "llama3.2:3b"
    assert record.purpose == "narrate"
    assert set(record.accepted_tools) <= _WHITELISTED_TOOLS


@pytest.mark.skipif(not _ollama_reachable(), reason=_REASON)
def test_propose_ranges_completes_a_genuine_round_trip_within_the_tool_whitelist() -> None:
    narrator = OllamaNarrator(model="llama3.2:3b", num_ctx=4096, timeout_s=45.0)
    ctx = HypothesisContext(
        model_id="macd_trend_0", family="trend",
        default_ranges={"fast": (5.0, 20.0), "slow": (20.0, 60.0)},
        degraded=False, drift_reasons=(), step=1,
    )

    ranges = narrator.propose_ranges(ctx)
    assert isinstance(ranges, dict)  # {} (fall back to the default space) is a legitimate answer

    calls = narrator.drain_calls()
    assert len(calls) == 1
    record = calls[0]
    assert record.purpose == "propose_space"
    assert set(record.accepted_tools) <= _WHITELISTED_TOOLS
