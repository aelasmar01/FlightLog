"""MCP JSON-RPC parsing helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Literal

from flightlog.mcp.models import McpMessage


def classify_jsonrpc_message(payload: dict[str, Any]) -> tuple[str, str | None, str | int | None]:
    method = payload.get("method")
    request_id = payload.get("id")
    if isinstance(method, str):
        if request_id is None:
            return "notification", method, None
        return "request", method, request_id
    if "result" in payload or "error" in payload:
        return "response", None, request_id
    return "notification", None, request_id


def parse_jsonrpc_payload(
    direction: Literal["client->server", "server->client"], text: str
) -> list[McpMessage]:
    stripped = text.strip()
    if not stripped:
        return []

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return []

    payloads: Iterable[Any]
    if isinstance(data, list):
        payloads = data
    else:
        payloads = [data]

    messages: list[McpMessage] = []
    for item in payloads:
        if not isinstance(item, dict):
            continue
        kind, method, request_id = classify_jsonrpc_message(item)
        messages.append(
            McpMessage(
                direction=direction,
                kind=kind,  # type: ignore[arg-type]
                method=method,
                request_id=request_id,
                payload=item,
            )
        )
    return messages
