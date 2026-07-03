"""The LLM tool-call schema (docs/11 §11.6, docs/02 §2.5): the *only* five
outputs a Narrator may emit into the loop. This module is the safety
boundary between a stochastic LLM and the deterministic engine.

Two structural guarantees live here, not in a runtime check:
- There is no tool type for placing/sizing an order, clearing the kill
  switch, or setting `validated`. The LLM literally cannot express those —
  the vocabulary doesn't contain them.
- `parse_tool_calls` is **fail-closed**: any element that doesn't validate
  as exactly one of the five whitelisted calls is dropped (and counted), so
  a hallucinated `{"tool": "place_order", ...}` or malformed blob can never
  reach the loop. Bad input degrades to "no tool calls", never to an
  unsafe action.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ProposeSpace(BaseModel):
    model_config = _FROZEN
    tool: Literal["propose_space"]
    model_id: str
    ranges: dict[str, list[float]]  # {"lookback": [10, 80]}
    rationale: str = ""


class RunTrials(BaseModel):
    model_config = _FROZEN
    tool: Literal["run_trials"]
    space_ref: str
    n_trials: int
    seed: int


class PromoteIfValid(BaseModel):
    model_config = _FROZEN
    tool: Literal["promote_if_valid"]
    candidate_id: str


class DeRisk(BaseModel):
    model_config = _FROZEN
    tool: Literal["de_risk"]
    model_id: str
    action: Literal["REDUCE", "PAUSE", "RETIRE"]


class Narrate(BaseModel):
    model_config = _FROZEN
    tool: Literal["narrate"]
    text: str
    refs: list[str] = []


ToolCall = ProposeSpace | RunTrials | PromoteIfValid | DeRisk | Narrate

_BY_NAME: dict[str, type[BaseModel]] = {
    "propose_space": ProposeSpace,
    "run_trials": RunTrials,
    "promote_if_valid": PromoteIfValid,
    "de_risk": DeRisk,
    "narrate": Narrate,
}

# The whitelist as a frozenset, handy for tests and for a fast membership
# check on a raw tool name before full validation.
WHITELIST: frozenset[str] = frozenset(_BY_NAME)


class ParseResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    calls: list[ToolCall]
    rejected: int  # how many elements were dropped (unknown/malformed) — for honest logging


def parse_tool_calls(raw: str | list[Any] | dict[str, Any] | None) -> ParseResult:
    """Fail-closed parse of raw LLM output into whitelisted `ToolCall`s.

    Accepts a JSON string, an already-parsed list of dicts, or a single
    dict. Anything that isn't exactly one of the five known tools — unknown
    tool name, missing/extra fields, wrong types, non-JSON — is dropped and
    counted in `rejected`. Never raises on bad input.
    """
    items = _coerce_to_items(raw)
    calls: list[ToolCall] = []
    rejected = 0
    for item in items:
        parsed = _parse_one(item)
        if parsed is None:
            rejected += 1
        else:
            calls.append(parsed)
    return ParseResult(calls=calls, rejected=rejected)


def _coerce_to_items(raw: str | list[Any] | dict[str, Any] | None) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
        return _coerce_to_items(decoded)
    if isinstance(raw, dict):
        # a chat response may wrap the calls, e.g. {"tool_calls": [...]}
        for key in ("tool_calls", "calls", "tools"):
            if key in raw and isinstance(raw[key], list):
                return list(raw[key])
        return [raw]
    if isinstance(raw, list):
        return list(raw)
    return []


def _parse_one(item: Any) -> ToolCall | None:
    if not isinstance(item, dict):
        return None
    name = item.get("tool")
    if not isinstance(name, str) or name not in _BY_NAME:
        return None
    model_cls = _BY_NAME[name]
    try:
        parsed = model_cls.model_validate(item)
    except ValidationError:
        return None
    assert isinstance(parsed, ProposeSpace | RunTrials | PromoteIfValid | DeRisk | Narrate)
    return parsed
