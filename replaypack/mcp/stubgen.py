"""Deterministic MCP stub generation from transcripts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from replaypack.json_utils import canonical_json_dumps
from replaypack.mcp.models import McpMessage
from replaypack.mcp.storage import iter_messages


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def params_hash(params: Any) -> str:
    normalized = canonicalize(params)
    payload = canonical_json_dumps(normalized).encode("utf-8")
    return sha256(payload).hexdigest()


def generate_stub(
    messages: Iterable[McpMessage], *, server_name: str | None = None
) -> dict[str, Any]:
    pending: dict[str, tuple[str, str]] = {}
    methods: dict[str, dict[str, dict[str, Any]]] = {}

    for message in messages:
        if (
            message.kind == "request"
            and message.request_id is not None
            and message.method is not None
        ):
            key = str(message.request_id)
            request_params = message.payload.get("params", {})
            pending[key] = (message.method, params_hash(request_params))
            continue

        if message.kind == "response" and message.request_id is not None:
            key = str(message.request_id)
            request_info = pending.pop(key, None)
            if request_info is None:
                continue
            method, request_hash = request_info
            method_map = methods.setdefault(method, {})
            response_payload: dict[str, Any] = {}
            if "result" in message.payload:
                response_payload["result"] = message.payload["result"]
            if "error" in message.payload:
                response_payload["error"] = message.payload["error"]
            method_map[request_hash] = canonicalize(response_payload)

    return {
        "schema_version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "server_name": server_name,
        "methods": {method: mapping for method, mapping in sorted(methods.items())},
        "fallback_rules": [],
    }


def write_stub(path: Path, stub_data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json_dumps(stub_data) + "\n", encoding="utf-8")


def generate_stub_from_transcript(
    transcript_path: Path, *, server_name: str | None = None
) -> dict[str, Any]:
    return generate_stub(iter_messages(transcript_path), server_name=server_name)


def load_stub(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Stub file must contain a JSON object")
    return data
