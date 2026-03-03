"""HTTP capture-record JSONL ingestion."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from flightlog.ingest.common import iter_jsonl
from flightlog.json_utils import canonical_json_dumps
from flightlog.llm.capture_record import CaptureRecord
from flightlog.llm.normalizers.select import select_normalizer
from flightlog.llm.to_events import to_events
from flightlog.models import NormalizedEvent

REQUIRED_CAPTURE_KEYS = {
    "ts",
    "session_id",
    "run_id",
    "provider_family",
    "request",
    "response",
    "transport",
}


def detect(input_path: Path) -> bool:
    try:
        for _, raw in iter_jsonl(input_path):
            return REQUIRED_CAPTURE_KEYS.issubset(set(raw.keys()))
    except Exception:
        return False
    return False


def iter_events(input_path: Path) -> Iterator[NormalizedEvent]:
    for line_no, raw in iter_jsonl(input_path):
        record = CaptureRecord.model_validate(raw)
        normalizer = select_normalizer(record.provider_family)
        turn = normalizer.normalize(
            raw_request=record.request.json_body,
            raw_response=record.response.json_body,
            meta={
                "provider": record.provider_family,
                "session_id": record.session_id,
                "timestamp": record.ts,
                "url": record.request.url,
                "status_code": record.response.status_code,
                "latency_ms": record.transport.latency_ms,
                "streaming": record.transport.streaming,
                "attempt": record.transport.attempt,
            },
        )
        events = to_events(
            turn,
            run_id=record.run_id,
            source="http_capture_jsonl",
            emit_tool_call_events=True,
            event_namespace=f"{input_path.name}:{line_no}",
        )
        yield from events


def extract_artifacts(input_path: Path) -> dict[str, bytes]:
    artifacts: dict[str, bytes] = {}
    for line_no, raw in iter_jsonl(input_path):
        record = CaptureRecord.model_validate(raw)
        request_key = f"capture/{record.session_id}/{line_no}_request.json"
        response_key = f"capture/{record.session_id}/{line_no}_response.json"
        request_payload = canonical_json_dumps(
            record.request.model_dump(mode="json", exclude_none=True)
        )
        response_payload = canonical_json_dumps(
            record.response.model_dump(mode="json", exclude_none=True)
        )
        artifacts[request_key] = (request_payload + "\n").encode("utf-8")
        artifacts[response_key] = (response_payload + "\n").encode("utf-8")
    return artifacts
