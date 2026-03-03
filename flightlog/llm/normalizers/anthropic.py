"""Anthropic payload normalization into canonical LLM turns."""

from __future__ import annotations

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


def _extract_text(block: Mapping[str, Any]) -> str | None:
    text_value = block.get("text")
    if isinstance(text_value, str):
        return text_value
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [item for item in content if isinstance(item, str)]
        if texts:
            return "\n".join(texts)
    return None


def _canonical_message_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        structured_parts: list[Any] = []
        for item in content:
            if isinstance(item, Mapping):
                block_type = str(item.get("type", ""))
                text = _extract_text(item)
                if block_type == "text" and text is not None:
                    text_parts.append(text)
                    continue
                structured_parts.append(canonicalize_json_value(dict(item)))
                continue
            structured_parts.append(canonicalize_json_value(item))
        if structured_parts:
            if text_parts:
                structured_parts.insert(0, {"type": "text", "text": "\n".join(text_parts)})
            return structured_parts
        if text_parts:
            return "\n".join(text_parts)
    return canonicalize_json_value(content)


def _content_to_messages(raw_request: Mapping[str, Any]) -> list[dict[str, Any]]:
    messages_value = raw_request.get("messages")
    if not isinstance(messages_value, Sequence):
        return []

    messages: list[dict[str, Any]] = []
    for item in messages_value:
        if not isinstance(item, Mapping):
            continue
        message: dict[str, Any] = {
            "role": str(item.get("role", "user")),
            "content": _canonical_message_content(item.get("content", "")),
        }
        messages.append(canonicalize_message(message))
    return messages


def _content_to_output_message(raw_response: Mapping[str, Any]) -> dict[str, Any]:
    role = str(raw_response.get("role", "assistant"))
    content = _canonical_message_content(raw_response.get("content", ""))
    message: dict[str, Any] = {
        "role": role,
        "content": content if content != "" else "",
    }
    return canonicalize_message(message)


def _extract_tool_calls(raw_response: Mapping[str, Any]) -> list[ToolCall]:
    blocks = raw_response.get("content")
    if not isinstance(blocks, Sequence):
        return []

    tool_calls: list[ToolCall] = []
    for index, item in enumerate(blocks):
        if not isinstance(item, Mapping):
            continue
        block_type = str(item.get("type", ""))
        if block_type != "tool_use":
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        input_value = item.get("input", {})
        arguments_json = canonicalize_json_value(input_value)
        if not isinstance(arguments_json, Mapping):
            arguments_json = {"value": arguments_json}
        tool_calls.append(
            ToolCall(
                id=str(item["id"]) if item.get("id") is not None else None,
                name=name,
                arguments_json=dict(arguments_json),
                index=index,
            )
        )
    return tool_calls


def _extract_usage(raw_response: Mapping[str, Any]) -> Usage | None:
    usage_value = raw_response.get("usage")
    if not isinstance(usage_value, Mapping):
        return None

    input_tokens = usage_value.get("input_tokens")
    output_tokens = usage_value.get("output_tokens")
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


class AnthropicNormalizer:
    """Normalize Anthropic request/response payloads into a single LLMTurn."""

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

        session_value = meta.get("session_id", "session")
        session_id = str(session_value)
        timestamp = _timestamp_from_meta(meta)

        input_messages = _content_to_messages(request_payload)
        output_message = _content_to_output_message(response_payload)
        tool_calls = _extract_tool_calls(response_payload)
        usage = _extract_usage(response_payload)
        transport = _extract_transport(meta)

        cost_value = meta.get("cost_usd")
        cost_usd = float(cost_value) if isinstance(cost_value, (int, float)) else None

        return LLMTurn(
            provider=str(meta.get("provider", "anthropic")),
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
