"""Generic codex-style JSONL ingestor."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from flightlog.ingest.common import (
    iter_jsonl,
    parse_timestamp,
    payload_without_meta,
    stringify_payload,
)
from flightlog.models import NormalizedEvent

GENERIC_META_KEYS = {
    "event_id",
    "id",
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
            return "type" in raw and any(k in raw for k in ("session_id", "run_id", "payload"))
    except Exception:
        return False
    return False


def iter_events(input_path: Path) -> Iterator[NormalizedEvent]:
    default_session = input_path.stem
    default_run = f"{input_path.stem}-run"
    for idx, (line_no, raw) in enumerate(iter_jsonl(input_path), start=1):
        event_type = str(raw.get("type", "unknown")).lower()
        source = str(raw.get("source", "codex_cli"))
        session_id = str(raw.get("session_id", default_session))
        run_id = str(raw.get("run_id", default_run))
        raw_event_id = raw.get("event_id") or raw.get("id")
        if isinstance(raw_event_id, str):
            event_id = raw_event_id
        else:
            event_id = str(uuid5(NAMESPACE_URL, f"{input_path.name}:{line_no}"))
        if isinstance(raw.get("payload"), dict):
            payload = dict(raw["payload"])
        else:
            payload = payload_without_meta(raw, GENERIC_META_KEYS)
        yield NormalizedEvent(
            event_id=event_id,
            ts=parse_timestamp(raw, idx),
            source=source,
            type=event_type,
            session_id=session_id,
            run_id=run_id,
            payload=payload,
        )


def extract_artifacts(input_path: Path) -> dict[str, bytes]:
    artifacts: dict[str, bytes] = {}
    for line_no, raw in iter_jsonl(input_path):
        session_id = str(raw.get("session_id", input_path.stem))
        payload = raw.get("payload")
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(value, (dict, list, str)):
                    artifact_key = f"ingest/{session_id}/{line_no}_{key}.json"
                    artifacts[artifact_key] = stringify_payload(value).encode("utf-8")
    return artifacts
