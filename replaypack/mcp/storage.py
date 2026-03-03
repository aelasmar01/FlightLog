"""Storage helpers for MCP transcripts and stubs."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from replaypack.json_utils import canonical_json_dumps
from replaypack.mcp.models import McpMessage


def transcript_path(root: Path, server_name: str, session_id: str) -> Path:
    path = root / "mcp" / "transcripts" / server_name / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def stub_path(root: Path, server_name: str, session_id: str) -> Path:
    path = root / "mcp" / "stubs" / server_name / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_message(path: Path, message: McpMessage) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json_dumps(message.model_dump(mode="json")))
        handle.write("\n")


def iter_messages(path: Path) -> Iterator[McpMessage]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            yield McpMessage.model_validate(data)
