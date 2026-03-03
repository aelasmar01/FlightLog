"""OpenAI-format message canonicalization helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from flightlog.llm.serialization import canonicalize_json_value


def canonicalize_tool_call(item: Mapping[str, Any]) -> dict[str, Any]:
    function = item.get("function", {})
    if not isinstance(function, Mapping):
        function = {}

    name_value = function.get("name", item.get("name", ""))
    args_value = function.get("arguments", item.get("arguments", {}))

    if isinstance(args_value, str):
        args = args_value
    else:
        args = canonicalize_json_value(args_value)

    result: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": str(name_value),
            "arguments": args,
        },
    }
    if "id" in item and item["id"] is not None:
        result["id"] = str(item["id"])
    if "index" in item and item["index"] is not None:
        result["index"] = int(item["index"])
    return result


def canonicalize_message(message: Mapping[str, Any]) -> dict[str, Any]:
    role_value = message.get("role", "user")
    result: dict[str, Any] = {"role": str(role_value)}

    if "content" in message:
        result["content"] = canonicalize_json_value(message["content"])
    else:
        result["content"] = ""

    if "name" in message and message["name"] is not None:
        result["name"] = str(message["name"])

    if "tool_call_id" in message and message["tool_call_id"] is not None:
        result["tool_call_id"] = str(message["tool_call_id"])

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        result["tool_calls"] = [
            canonicalize_tool_call(item) for item in tool_calls if isinstance(item, Mapping)
        ]

    return result


def canonicalize_messages(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [canonicalize_message(message) for message in messages]
