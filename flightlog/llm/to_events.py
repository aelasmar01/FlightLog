"""Convert canonical LLM turns to normalized timeline events."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from flightlog.json_utils import canonical_json_dumps
from flightlog.llm.message_schema import canonicalize_message, canonicalize_messages
from flightlog.llm.models import LLMTurn, ToolCall
from flightlog.llm.serialization import canonicalize_json_value
from flightlog.models import NormalizedEvent


def _stable_event_id(
    turn: LLMTurn,
    run_id: str,
    event_type: str,
    index: int,
    namespace: str | None,
) -> str:
    payload = {
        "provider": turn.provider,
        "session_id": turn.session_id,
        "run_id": run_id,
        "timestamp": turn.timestamp.isoformat(),
        "event_type": event_type,
        "index": index,
    }
    if namespace is not None:
        payload["namespace"] = namespace
    return str(uuid5(NAMESPACE_URL, canonical_json_dumps(payload)))


def _tool_call_payload(tool_call: ToolCall) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": tool_call.name,
        "arguments_json": canonicalize_json_value(tool_call.arguments_json),
    }
    if tool_call.id is not None:
        payload["id"] = tool_call.id
    if tool_call.index is not None:
        payload["index"] = tool_call.index
    return payload


def _common_payload(turn: LLMTurn) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": turn.provider,
        "messages": canonicalize_messages(turn.input_messages),
        "tool_calls": [_tool_call_payload(tool_call) for tool_call in turn.tool_calls],
    }
    if turn.model is not None:
        payload["model"] = turn.model
    if turn.usage is not None:
        payload["usage"] = canonicalize_json_value(
            turn.usage.model_dump(mode="json", exclude_none=True)
        )
    if turn.cost_usd is not None:
        payload["cost_usd"] = turn.cost_usd
    if turn.transport is not None:
        payload["transport"] = canonicalize_json_value(
            turn.transport.model_dump(mode="json", exclude_none=True)
        )
    return payload


def to_events(
    turn: LLMTurn,
    *,
    run_id: str | None = None,
    source: str = "llm.normalized",
    emit_tool_call_events: bool = True,
    event_namespace: str | None = None,
) -> list[NormalizedEvent]:
    resolved_run_id = run_id if run_id is not None else f"{turn.session_id}-turn"
    request_payload = _common_payload(turn)
    if turn.raw_request is not None:
        request_payload["raw_request"] = canonicalize_json_value(turn.raw_request)

    response_payload = _common_payload(turn)
    if turn.output_message is not None:
        response_payload["output_message"] = canonicalize_message(turn.output_message)
    else:
        response_payload["output_message"] = {"role": "assistant", "content": ""}
    if turn.raw_response is not None:
        response_payload["raw_response"] = canonicalize_json_value(turn.raw_response)

    events: list[NormalizedEvent] = [
        NormalizedEvent(
            event_id=_stable_event_id(
                turn,
                resolved_run_id,
                "model.request",
                0,
                event_namespace,
            ),
            ts=turn.timestamp,
            source=source,
            type="model.request",
            session_id=turn.session_id,
            run_id=resolved_run_id,
            payload=request_payload,
        ),
        NormalizedEvent(
            event_id=_stable_event_id(
                turn,
                resolved_run_id,
                "model.response",
                0,
                event_namespace,
            ),
            ts=turn.timestamp,
            source=source,
            type="model.response",
            session_id=turn.session_id,
            run_id=resolved_run_id,
            payload=response_payload,
        ),
    ]

    if emit_tool_call_events:
        for index, tool_call in enumerate(turn.tool_calls):
            events.append(
                NormalizedEvent(
                    event_id=_stable_event_id(
                        turn,
                        resolved_run_id,
                        "tool.call",
                        index,
                        event_namespace,
                    ),
                    ts=turn.timestamp,
                    source=source,
                    type="tool.call",
                    session_id=turn.session_id,
                    run_id=resolved_run_id,
                    payload={
                        "provider": turn.provider,
                        "model": turn.model,
                        "tool_call": _tool_call_payload(tool_call),
                    },
                )
            )
    return events
