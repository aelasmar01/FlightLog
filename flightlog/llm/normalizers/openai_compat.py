"""OpenAI-compatible payload normalization into canonical LLM turns."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from flightlog.llm.message_schema import canonicalize_message
from flightlog.llm.models import LLMTurn, ToolCall, TransportMeta, Usage
from flightlog.llm.serialization import canonicalize_json_value


def _timestamp_from_meta(meta: Mapping[str, Any]) -> datetime:
    value = meta.get("timestamp")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    return datetime.now(UTC)


def _request_messages(raw_request: Mapping[str, Any]) -> list[dict[str, Any]]:
    messages_value = raw_request.get("messages")
    if not isinstance(messages_value, Sequence):
        return []
    messages: list[dict[str, Any]] = []
    for item in messages_value:
        if not isinstance(item, Mapping):
            continue
        messages.append(canonicalize_message(dict(item)))
    return messages


def _response_message(raw_response: Mapping[str, Any]) -> dict[str, Any]:
    choices_value = raw_response.get("choices")
    if isinstance(choices_value, Sequence):
        for item in choices_value:
            if not isinstance(item, Mapping):
                continue
            message_value = item.get("message")
            if isinstance(message_value, Mapping):
                return canonicalize_message(dict(message_value))
    message_value = raw_response.get("message")
    if isinstance(message_value, Mapping):
        return canonicalize_message(dict(message_value))
    return {"role": "assistant", "content": ""}


def _parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(canonicalize_json_value(value))
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        if isinstance(parsed, Mapping):
            return dict(canonicalize_json_value(parsed))
        return {"value": canonicalize_json_value(parsed)}
    return {"value": canonicalize_json_value(value)}


def _extract_tool_calls(raw_response: Mapping[str, Any]) -> list[ToolCall]:
    message = _response_message(raw_response)
    tool_calls_value = message.get("tool_calls")
    tool_calls: list[ToolCall] = []

    if isinstance(tool_calls_value, list):
        for index, item in enumerate(tool_calls_value):
            if not isinstance(item, Mapping):
                continue
            function_value = item.get("function")
            if not isinstance(function_value, Mapping):
                continue
            name_value = function_value.get("name")
            if not isinstance(name_value, str) or not name_value:
                continue
            arguments_json = _parse_arguments(function_value.get("arguments", {}))
            tool_calls.append(
                ToolCall(
                    id=str(item["id"]) if item.get("id") is not None else None,
                    name=name_value,
                    arguments_json=arguments_json,
                    index=index,
                )
            )
        return tool_calls

    function_call = message.get("function_call")
    if isinstance(function_call, Mapping):
        name_value = function_call.get("name")
        if isinstance(name_value, str) and name_value:
            tool_calls.append(
                ToolCall(
                    id=None,
                    name=name_value,
                    arguments_json=_parse_arguments(function_call.get("arguments", {})),
                    index=0,
                )
            )
    return tool_calls


def _extract_usage(raw_response: Mapping[str, Any]) -> Usage | None:
    usage_value = raw_response.get("usage")
    if not isinstance(usage_value, Mapping):
        return None
    input_tokens = usage_value.get("prompt_tokens", usage_value.get("input_tokens"))
    output_tokens = usage_value.get("completion_tokens", usage_value.get("output_tokens"))
    total_tokens = usage_value.get("total_tokens")
    if (
        not isinstance(input_tokens, int)
        and not isinstance(output_tokens, int)
        and not isinstance(total_tokens, int)
    ):
        return None
    return Usage(
        input_tokens=input_tokens if isinstance(input_tokens, int) else None,
        output_tokens=output_tokens if isinstance(output_tokens, int) else None,
        total_tokens=total_tokens if isinstance(total_tokens, int) else None,
    )


def _extract_transport(meta: Mapping[str, Any]) -> TransportMeta | None:
    transport_value = meta.get("transport")
    if isinstance(transport_value, Mapping):
        base = dict(transport_value)
    else:
        base = {}
    for key in ("url", "status_code", "latency_ms", "streaming", "attempt", "request_id"):
        if key in meta and key not in base:
            base[key] = meta[key]
    if not base:
        return None
    return TransportMeta.model_validate(base)


class OpenAICompatNormalizer:
    """Normalize OpenAI/Azure-compatible payloads into a canonical LLMTurn."""

    def normalize(
        self,
        raw_request: Mapping[str, Any] | None,
        raw_response: Mapping[str, Any] | None,
        meta: Mapping[str, Any],
    ) -> LLMTurn:
        request_payload = dict(raw_request or {})
        response_payload = dict(raw_response or {})

        model_value = response_payload.get("model", request_payload.get("model"))
        model = str(model_value) if isinstance(model_value, str) else None

        session_id = str(meta.get("session_id", "session"))
        timestamp = _timestamp_from_meta(meta)
        input_messages = _request_messages(request_payload)
        output_message = _response_message(response_payload)
        tool_calls = _extract_tool_calls(response_payload)
        usage = _extract_usage(response_payload)
        transport = _extract_transport(meta)

        cost_value = meta.get("cost_usd")
        cost_usd = float(cost_value) if isinstance(cost_value, (int, float)) else None

        return LLMTurn(
            provider=str(meta.get("provider", "openai_compat")),
            model=model,
            session_id=session_id,
            timestamp=timestamp,
            input_messages=input_messages,
            output_message=output_message,
            tool_calls=tool_calls,
            usage=usage,
            cost_usd=cost_usd,
            raw_request=canonicalize_json_value(request_payload) if request_payload else None,
            raw_response=canonicalize_json_value(response_payload) if response_payload else None,
            transport=transport,
        )
