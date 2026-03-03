"""Gemini payload normalization into canonical LLM turns."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from flightlog.llm.message_schema import canonicalize_message
from flightlog.llm.models import LLMTurn, ToolCall, TransportMeta, Usage
from flightlog.llm.serialization import canonicalize_json_value


class GeminiNormalizer:
    """Normalize Gemini request/response payloads into a canonical LLMTurn."""

    def _timestamp_from_meta(self, meta: Mapping[str, Any]) -> datetime:
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

    def _role_to_openai(self, role: str) -> str:
        normalized = role.strip().lower()
        if normalized == "model":
            return "assistant"
        return normalized if normalized else "user"

    def _parts_to_content(self, parts_value: Any) -> Any:
        if not isinstance(parts_value, Sequence):
            return ""
        text_parts: list[str] = []
        structured_parts: list[Any] = []
        for item in parts_value:
            if not isinstance(item, Mapping):
                continue
            text = item.get("text")
            if isinstance(text, str):
                text_parts.append(text)
                continue
            function_call = item.get("functionCall")
            if isinstance(function_call, Mapping):
                structured_parts.append({"type": "function_call", "function_call": function_call})
                continue
            function_response = item.get("functionResponse")
            if isinstance(function_response, Mapping):
                structured_parts.append(
                    {"type": "function_response", "function_response": function_response}
                )
                continue
            structured_parts.append(canonicalize_json_value(item))
        if structured_parts:
            if text_parts:
                structured_parts.insert(0, {"type": "text", "text": "\n".join(text_parts)})
            return canonicalize_json_value(structured_parts)
        if text_parts:
            return "\n".join(text_parts)
        return ""

    def _request_messages(self, raw_request: Mapping[str, Any]) -> list[dict[str, Any]]:
        contents_value = raw_request.get("contents")
        if not isinstance(contents_value, Sequence):
            return []
        messages: list[dict[str, Any]] = []
        for item in contents_value:
            if not isinstance(item, Mapping):
                continue
            role_value = item.get("role")
            role = self._role_to_openai(str(role_value)) if isinstance(role_value, str) else "user"
            message = {
                "role": role,
                "content": self._parts_to_content(item.get("parts", [])),
            }
            messages.append(canonicalize_message(message))
        return messages

    def _candidate(self, raw_response: Mapping[str, Any]) -> Mapping[str, Any]:
        candidates_value = raw_response.get("candidates")
        if isinstance(candidates_value, Sequence):
            for item in candidates_value:
                if isinstance(item, Mapping):
                    return item
        return {}

    def _output_message(self, raw_response: Mapping[str, Any]) -> dict[str, Any]:
        candidate = self._candidate(raw_response)
        content_value = candidate.get("content")
        if isinstance(content_value, Mapping):
            role_value = content_value.get("role")
            role = (
                self._role_to_openai(str(role_value))
                if isinstance(role_value, str)
                else "assistant"
            )
            return canonicalize_message(
                {
                    "role": role,
                    "content": self._parts_to_content(content_value.get("parts", [])),
                }
            )
        return {"role": "assistant", "content": ""}

    def _tool_calls(self, raw_response: Mapping[str, Any]) -> list[ToolCall]:
        candidate = self._candidate(raw_response)
        content_value = candidate.get("content")
        if not isinstance(content_value, Mapping):
            return []
        parts_value = content_value.get("parts")
        if not isinstance(parts_value, Sequence):
            return []
        tool_calls: list[ToolCall] = []
        for index, item in enumerate(parts_value):
            if not isinstance(item, Mapping):
                continue
            function_call = item.get("functionCall")
            if not isinstance(function_call, Mapping):
                continue
            name_value = function_call.get("name")
            if not isinstance(name_value, str) or not name_value:
                continue
            args_value = function_call.get("args", {})
            canonical_args = canonicalize_json_value(args_value)
            if not isinstance(canonical_args, Mapping):
                canonical_args = {"value": canonical_args}
            tool_calls.append(
                ToolCall(
                    id=str(function_call["id"]) if function_call.get("id") is not None else None,
                    name=name_value,
                    arguments_json=dict(canonical_args),
                    index=index,
                )
            )
        return tool_calls

    def _usage(self, raw_response: Mapping[str, Any]) -> Usage | None:
        usage_value = raw_response.get("usageMetadata")
        if not isinstance(usage_value, Mapping):
            return None
        input_tokens = usage_value.get("promptTokenCount")
        output_tokens = usage_value.get("candidatesTokenCount")
        total_tokens = usage_value.get("totalTokenCount")
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

    def _transport(self, meta: Mapping[str, Any]) -> TransportMeta | None:
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

    def normalize(
        self,
        raw_request: Mapping[str, Any] | None,
        raw_response: Mapping[str, Any] | None,
        meta: Mapping[str, Any],
    ) -> LLMTurn:
        request_payload = dict(raw_request or {})
        response_payload = dict(raw_response or {})

        model_value = (
            request_payload.get("model")
            or response_payload.get("modelVersion")
            or response_payload.get("model")
        )
        model = str(model_value) if isinstance(model_value, str) else None

        session_id = str(meta.get("session_id", "session"))
        timestamp = self._timestamp_from_meta(meta)

        usage = self._usage(response_payload)
        transport = self._transport(meta)
        cost_value = meta.get("cost_usd")
        cost_usd = float(cost_value) if isinstance(cost_value, (int, float)) else None

        return LLMTurn(
            provider=str(meta.get("provider", "gemini")),
            model=model,
            session_id=session_id,
            timestamp=timestamp,
            input_messages=self._request_messages(request_payload),
            output_message=self._output_message(response_payload),
            tool_calls=self._tool_calls(response_payload),
            usage=usage,
            cost_usd=cost_usd,
            raw_request=canonicalize_json_value(request_payload) if request_payload else None,
            raw_response=canonicalize_json_value(response_payload) if response_payload else None,
            transport=transport,
        )
