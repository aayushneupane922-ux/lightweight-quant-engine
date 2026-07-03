"""The LLM tool vocabulary is the safety boundary (docs/11 §11.6, docs/02
§2.5): the only five outputs exist, and the parser is fail-closed. An LLM
can therefore never express placing/sizing an order, clearing the kill
switch, or setting `validated` — those tools simply do not exist, and any
attempt to invoke them is dropped.
"""

from __future__ import annotations

from lqe.autonomy.tools import (
    WHITELIST,
    Narrate,
    ProposeSpace,
    parse_tool_calls,
)


def test_the_vocabulary_is_exactly_the_five_whitelisted_tools() -> None:
    assert {
        "propose_space", "run_trials", "promote_if_valid", "de_risk", "narrate"
    } == WHITELIST
    # nothing order/kill/validated-shaped is in the vocabulary
    for forbidden in ("place_order", "submit_order", "clear_kill", "set_validated", "size"):
        assert forbidden not in WHITELIST


def test_parser_accepts_only_valid_whitelisted_calls() -> None:
    raw = [
        {"tool": "propose_space", "model_id": "m", "ranges": {"fast": [2, 20]}, "rationale": "x"},
        {"tool": "narrate", "text": "hello", "refs": []},
    ]
    result = parse_tool_calls(raw)
    assert [c.tool for c in result.calls] == ["propose_space", "narrate"]
    assert result.rejected == 0
    assert isinstance(result.calls[0], ProposeSpace)
    assert isinstance(result.calls[1], Narrate)


def test_parser_drops_dangerous_tool_names_fail_closed() -> None:
    raw = [
        {"tool": "place_order", "symbol": "BTC-USDT", "qty": 1000},
        {"tool": "clear_kill", "operator": "attacker"},
        {"tool": "set_validated", "candidate_id": "c1"},
        {"tool": "narrate", "text": "legit", "refs": []},
    ]
    result = parse_tool_calls(raw)
    assert [c.tool for c in result.calls] == ["narrate"]  # only the legit one survives
    assert result.rejected == 3


def test_parser_drops_malformed_and_never_raises() -> None:
    assert parse_tool_calls("not json at all").calls == []
    assert parse_tool_calls(None).calls == []
    assert parse_tool_calls([{"garbage": True}, "string", 42]).calls == []
    # a known tool with wrong/extra fields is rejected (extra=forbid)
    bad = parse_tool_calls([{"tool": "de_risk", "model_id": "m", "action": "SELL_EVERYTHING"}])
    assert bad.calls == [] and bad.rejected == 1


def test_parser_reads_a_chat_wrapped_tool_calls_list() -> None:
    wrapped = {"tool_calls": [{"tool": "promote_if_valid", "candidate_id": "c1"}]}
    result = parse_tool_calls(wrapped)
    assert [c.tool for c in result.calls] == ["promote_if_valid"]


def test_promote_if_valid_carries_only_a_candidate_id_no_verdict() -> None:
    # the LLM can request promotion but cannot assert a verdict — the tool
    # has no field for it; only the gate decides PASS/FAIL.
    result = parse_tool_calls([{"tool": "promote_if_valid", "candidate_id": "c1"}])
    call = result.calls[0]
    assert set(call.model_dump()) == {"tool", "candidate_id"}
