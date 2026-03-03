"""Claude Code JSONL ingestion."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from replaypack.ingest.common import (
    iter_jsonl,
    parse_timestamp,
    payload_without_meta,
    stringify_payload,
)
from replaypack.models import NormalizedEvent

CLAUDE_EVENT_KEYS = {
    "type",
    "ts",
    "timestamp",
    "time",
    "session_id",
    "run_id",
    "source",
}


def detect(input_path: Path) -> bool:
    try:
        for _, raw in iter_jsonl(input_path):
            source = str(raw.get("source", "")).lower()
            if source == "claude_code":
                return True
            if "claude" in str(raw.get("client", "")).lower():
                return True
            event_type = str(raw.get("type", "")).lower()
            if event_type.startswith("claude.") or event_type.startswith("tool."):
                return True
            return False
    except Exception:
        return False
    return False


def _map_event_type(raw_type: str) -> str:
    normalized = raw_type.strip().lower()
    if not normalized:
        return "unknown"
    if normalized in {"request", "model_request"}:
        return "model.request"
    if normalized in {"response", "model_response"}:
        return "model.response"
    if normalized in {"tool_use", "tool.call"}:
        return "tool.call"
    if normalized in {"tool_result", "tool.output", "tool.result"}:
        return "tool.result"
    if normalized == "file.diff":
        return "file.diff"
    return normalized


def iter_events(input_path: Path) -> Iterator[NormalizedEvent]:
    default_session = input_path.stem
    default_run = f"{input_path.stem}-run"
    for idx, (line_no, raw) in enumerate(iter_jsonl(input_path), start=1):
        raw_type = str(raw.get("type", "unknown"))
        session_id = str(raw.get("session_id", default_session))
        run_id = str(raw.get("run_id", default_run))
        raw_event_id = raw.get("event_id") or raw.get("id")
        if isinstance(raw_event_id, str):
            event_id = raw_event_id
        else:
            event_id = str(uuid5(NAMESPACE_URL, f"{input_path.name}:{line_no}"))
        payload = payload_without_meta(raw, CLAUDE_EVENT_KEYS)
        yield NormalizedEvent(
            event_id=event_id,
            ts=parse_timestamp(raw, idx),
            source="claude_code",
            type=_map_event_type(raw_type),
            session_id=session_id,
            run_id=run_id,
            payload=payload,
        )


def extract_artifacts(input_path: Path) -> dict[str, bytes]:
    artifacts: dict[str, bytes] = {}
    for line_no, raw in iter_jsonl(input_path):
        session_id = str(raw.get("session_id", input_path.stem))
        for key in ("prompt", "response", "tool_input", "tool_output", "stdout", "stderr"):
            if key not in raw:
                continue
            content = stringify_payload(raw[key])
            artifact_key = f"ingest/{session_id}/{line_no}_{key}.txt"
            artifacts[artifact_key] = content.encode("utf-8")
    return artifacts
