"""Deterministic serialization helpers for LLM turns."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from flightlog.json_utils import canonical_json_dumps
from flightlog.llm.models import LLMTurn


def canonicalize_json_value(value: Any) -> Any:
    """Normalize nested mappings/lists to deterministic key ordering."""
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda item: str(item[0]))
        return {str(key): canonicalize_json_value(item) for key, item in items}
    if isinstance(value, list):
        return [canonicalize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [canonicalize_json_value(item) for item in value]
    return value


def dumps_turn(turn: LLMTurn) -> str:
    data = turn.model_dump(mode="json", exclude_none=True)
    return canonical_json_dumps(canonicalize_json_value(data))


def loads_turn(payload: str) -> LLMTurn:
    raw = json.loads(payload)
    return LLMTurn.model_validate(canonicalize_json_value(raw))
