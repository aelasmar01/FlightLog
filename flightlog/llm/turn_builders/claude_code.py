"""Build canonical LLM turns from Claude Code JSONL event streams."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from flightlog.ingest.common import parse_timestamp, payload_without_meta
from flightlog.llm.models import LLMTurn
from flightlog.llm.normalizers.anthropic import AnthropicNormalizer
from flightlog.llm.serialization import canonicalize_json_value

CLAUDE_EVENT_KEYS = {
    "event_id",
    "id",
    "type",
    "ts",
    "timestamp",
    "time",
    "session_id",
    "run_id",
    "source",
}


@dataclass(frozen=True, slots=True)
class BuiltTurn:
    turn: LLMTurn
    run_id: str
    request_line_no: int
    response_line_no: int
    request_index: int
    response_index: int
    request_context: dict[str, Any]


@dataclass(slots=True)
class _ActiveTurn:
    session_id: str
    run_id: str
    request_line_no: int
    request_index: int
    request_ts: datetime
    request_payload: dict[str, Any]
    response_line_no: int | None = None
    response_index: int | None = None
    response_payload: dict[str, Any] | None = None
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)


def _map_event_type(raw_type: str) -> str:
    normalized = raw_type.strip().lower()
    if normalized in {"request", "model_request"}:
        return "model.request"
    if normalized in {"response", "model_response"}:
        return "model.response"
    if normalized in {"tool_use", "tool.call"}:
        return "tool.call"
    if normalized in {"tool_result", "tool.output", "tool.result"}:
        return "tool.result"
    return normalized


def _extract_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _tool_use_block(payload: dict[str, Any]) -> dict[str, Any] | None:
    name_value = payload.get("name") or payload.get("tool_name") or payload.get("tool")
    if not isinstance(name_value, str) or not name_value:
        return None

    identifier_value = payload.get("id") or payload.get("tool_use_id") or payload.get("tool_id")
    input_value = payload.get("tool_input", payload.get("input", payload.get("arguments", {})))
    canonical_input = canonicalize_json_value(input_value)
    if not isinstance(canonical_input, dict):
        canonical_input = {"value": canonical_input}

    block: dict[str, Any] = {
        "type": "tool_use",
        "name": name_value,
        "input": canonical_input,
    }
    if identifier_value is not None:
        block["id"] = str(identifier_value)
    return block


def _tool_result_block(payload: dict[str, Any]) -> dict[str, Any]:
    identifier_value = payload.get("tool_use_id") or payload.get("tool_id") or payload.get("id")
    content_value = payload.get(
        "tool_output",
        payload.get("output", payload.get("result", payload.get("content", payload))),
    )
    block: dict[str, Any] = {
        "type": "tool_result",
        "content": canonicalize_json_value(content_value),
    }
    if identifier_value is not None:
        block["tool_use_id"] = str(identifier_value)
    return block


def _build_request_payload(active: _ActiveTurn) -> dict[str, Any]:
    request_payload = dict(active.request_payload)
    messages_value = request_payload.get("messages")
    if isinstance(messages_value, list):
        result: dict[str, Any] = {"messages": canonicalize_json_value(messages_value)}
    else:
        blocks: list[dict[str, Any]] = []
        prompt_text = _extract_text(
            request_payload,
            (
                "prompt",
                "input",
                "input_text",
                "query",
                "message",
            ),
        )
        if prompt_text is not None:
            blocks.append({"type": "text", "text": prompt_text})
        blocks.extend(_tool_result_block(item) for item in active.tool_results)
        if blocks:
            result = {"messages": [{"role": "user", "content": blocks}]}
        else:
            result = {"messages": []}

    model_value = request_payload.get("model")
    if isinstance(model_value, str):
        result["model"] = model_value
    return result


def _build_response_payload(active: _ActiveTurn) -> dict[str, Any]:
    base_payload = dict(active.response_payload or {})
    content_value = base_payload.get("content")
    blocks: list[dict[str, Any]]
    if isinstance(content_value, list):
        blocks = [item for item in content_value if isinstance(item, dict)]
    else:
        blocks = []
        response_text = _extract_text(
            base_payload,
            (
                "response",
                "output",
                "text",
                "message",
            ),
        )
        if response_text is not None:
            blocks.append({"type": "text", "text": response_text})

    for tool_payload in active.tool_uses:
        block = _tool_use_block(tool_payload)
        if block is not None:
            blocks.append(block)

    result: dict[str, Any] = {"role": "assistant", "content": canonicalize_json_value(blocks)}
    model_value = base_payload.get("model")
    if isinstance(model_value, str):
        result["model"] = model_value
    usage_value = base_payload.get("usage")
    if isinstance(usage_value, dict):
        result["usage"] = canonicalize_json_value(usage_value)
    return result


def _flush_turn(active: _ActiveTurn, normalizer: AnthropicNormalizer) -> BuiltTurn:
    request_payload = _build_request_payload(active)
    response_payload = _build_response_payload(active)
    turn = normalizer.normalize(
        raw_request=request_payload,
        raw_response=response_payload,
        meta={
            "provider": "anthropic",
            "session_id": active.session_id,
            "timestamp": active.request_ts,
        },
    )
    return BuiltTurn(
        turn=turn,
        run_id=active.run_id,
        request_line_no=active.request_line_no,
        response_line_no=active.response_line_no or active.request_line_no,
        request_index=active.request_index,
        response_index=active.response_index or active.request_index,
        request_context=canonicalize_json_value(active.request_payload),
    )


def _new_active_turn(
    *,
    session_id: str,
    run_id: str,
    line_no: int,
    index: int,
    ts: datetime,
    request_payload: dict[str, Any],
) -> _ActiveTurn:
    return _ActiveTurn(
        session_id=session_id,
        run_id=run_id,
        request_line_no=line_no,
        request_index=index,
        request_ts=ts,
        request_payload=request_payload,
    )


def build_turns(
    rows: list[tuple[int, dict[str, Any]]],
    *,
    default_session: str,
    default_run: str,
) -> list[BuiltTurn]:
    normalizer = AnthropicNormalizer()
    active_by_key: dict[tuple[str, str], _ActiveTurn] = {}
    pending_tool_results: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    built: list[BuiltTurn] = []

    for index, (line_no, raw) in enumerate(rows, start=1):
        session_id = str(raw.get("session_id", default_session))
        run_id = str(raw.get("run_id", default_run))
        key = (session_id, run_id)
        event_type = _map_event_type(str(raw.get("type", "")))
        payload = payload_without_meta(raw, CLAUDE_EVENT_KEYS)
        if event_type in {"tool.call", "tool.result"}:
            tool_identifier = raw.get("tool_use_id", raw.get("id"))
            if tool_identifier is not None and "tool_use_id" not in payload:
                payload["tool_use_id"] = str(tool_identifier)
        ts = parse_timestamp(raw, index)

        if event_type == "model.request":
            existing = active_by_key.get(key)
            if existing is not None:
                built.append(_flush_turn(existing, normalizer))
            request_turn = _new_active_turn(
                session_id=session_id,
                run_id=run_id,
                line_no=line_no,
                index=index,
                ts=ts,
                request_payload=payload,
            )
            if key in pending_tool_results:
                request_turn.tool_results.extend(pending_tool_results.pop(key))
            active_by_key[key] = request_turn
            continue

        if event_type == "tool.call":
            call_turn = active_by_key.get(key)
            if call_turn is None:
                call_turn = _new_active_turn(
                    session_id=session_id,
                    run_id=run_id,
                    line_no=line_no,
                    index=index,
                    ts=ts,
                    request_payload={},
                )
                if key in pending_tool_results:
                    call_turn.tool_results.extend(pending_tool_results.pop(key))
                active_by_key[key] = call_turn
            call_turn.tool_uses.append(payload)
            continue

        if event_type == "tool.result":
            result_turn = active_by_key.get(key)
            if result_turn is None:
                pending_tool_results[key].append(payload)
            else:
                result_turn.tool_results.append(payload)
            continue

        if event_type == "model.response":
            response_turn = active_by_key.get(key)
            if response_turn is None:
                response_turn = _new_active_turn(
                    session_id=session_id,
                    run_id=run_id,
                    line_no=line_no,
                    index=index,
                    ts=ts,
                    request_payload={},
                )
                if key in pending_tool_results:
                    response_turn.tool_results.extend(pending_tool_results.pop(key))
                active_by_key[key] = response_turn
            response_turn.response_line_no = line_no
            response_turn.response_index = index
            response_turn.response_payload = payload
            built.append(_flush_turn(response_turn, normalizer))
            del active_by_key[key]

    for active_turn in sorted(active_by_key.values(), key=lambda item: item.request_index):
        built.append(_flush_turn(active_turn, normalizer))
    return built
