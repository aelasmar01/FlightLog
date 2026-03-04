"""MCP JSON-RPC parsing helpers."""

from __future__ import annotations

import json
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


def _extract_json_objects(text: str) -> list[Any]:
    """Parse a text body that may be plain JSON or SSE-formatted JSON-RPC.

    SSE lines look like ``data: <json>``; each is parsed independently.
    Plain JSON (single object or array) is also handled.
    """
    stripped = text.strip()
    if not stripped:
        return []

    # Fast path: plain JSON.
    try:
        result = json.loads(stripped)
        return result if isinstance(result, list) else [result]
    except json.JSONDecodeError:
        pass

    # SSE format: collect all `data: <json>` lines.
    objects: list[Any] = []
    for line in stripped.splitlines():
        if not line.startswith("data:"):
            continue
        json_str = line[5:].lstrip(" ")
        try:
            objects.append(json.loads(json_str))
        except json.JSONDecodeError:
            continue
    return objects


def parse_jsonrpc_payload(
    direction: Literal["client->server", "server->client"], text: str
) -> list[McpMessage]:
    objects = _extract_json_objects(text)

    messages: list[McpMessage] = []
    for item in objects:
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
