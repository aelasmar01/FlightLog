"""Ingestor selection and entrypoints."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from flightlog.ingest import claude_code, generic_jsonl, http_capture_jsonl
from flightlog.models import NormalizedEvent


@dataclass(frozen=True, slots=True)
class Ingestor:
    name: str
    detect: Callable[[Path], bool]
    iter_events: Callable[[Path], Iterator[NormalizedEvent]]
    extract_artifacts: Callable[[Path], dict[str, bytes]]


# Deterministic precedence if multiple detectors match.
_INGESTORS: tuple[Ingestor, ...] = (
    Ingestor(
        name="claude_code",
        detect=claude_code.detect,
        iter_events=claude_code.iter_events,
        extract_artifacts=claude_code.extract_artifacts,
    ),
    Ingestor(
        name="http_capture_jsonl",
        detect=http_capture_jsonl.detect,
        iter_events=http_capture_jsonl.iter_events,
        extract_artifacts=http_capture_jsonl.extract_artifacts,
    ),
    Ingestor(
        name="generic_jsonl",
        detect=generic_jsonl.detect,
        iter_events=generic_jsonl.iter_events,
        extract_artifacts=generic_jsonl.extract_artifacts,
    ),
)


def select_ingestor(input_path: Path) -> Ingestor:
    for ingestor in _INGESTORS:
        if ingestor.detect(input_path):
            return ingestor
    raise ValueError(f"No ingestor detected for {input_path}")


def list_ingestors() -> tuple[str, ...]:
    return tuple(item.name for item in _INGESTORS)
