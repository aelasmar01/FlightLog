from pathlib import Path

from replaypack.ingest.generic_jsonl import detect, extract_artifacts, iter_events
from replaypack.json_utils import canonical_json_dumps


def test_generic_ingest_golden() -> None:
    fixture = Path("tests/fixtures/generic_jsonl/generic_session.jsonl")
    expected = Path("tests/fixtures/generic_jsonl/expected_timeline.jsonl")

    assert detect(fixture)
    events = list(iter_events(fixture))
    actual_lines = [canonical_json_dumps(event.to_dict()) for event in events]
    expected_lines = [
        line.strip() for line in expected.read_text(encoding="utf-8").splitlines() if line.strip()
    ]

    assert actual_lines == expected_lines


def test_generic_extract_artifacts() -> None:
    fixture = Path("tests/fixtures/generic_jsonl/generic_session.jsonl")
    artifacts = extract_artifacts(fixture)
    assert artifacts
    assert all(key.startswith("ingest/") for key in artifacts)
