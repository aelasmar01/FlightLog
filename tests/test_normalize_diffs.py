from pathlib import Path

from replaypack.ingest.claude_code import iter_events
from replaypack.models import NormalizedEvent
from replaypack.normalize import normalize_events


def test_large_payload_moves_to_artifact() -> None:
    events = [
        NormalizedEvent(
            event_id="evt-large",
            source="test",
            type="model.response",
            session_id="s",
            run_id="r",
            payload={"text": "x" * 20},
        )
    ]

    normalized, artifacts = normalize_events(events, artifact_threshold_bytes=8)
    payload = normalized[0].payload
    assert isinstance(payload["text"], dict)
    assert "artifact_ref" in payload["text"]
    assert artifacts


def test_log_derived_diff_fixture() -> None:
    fixture = Path("tests/fixtures/diffs/log_derived/log_diff.jsonl")
    expected_patch = Path("tests/fixtures/diffs/log_derived/expected.patch").read_text(
        encoding="utf-8"
    )

    events = list(iter_events(fixture))
    normalized, artifacts = normalize_events(events)

    diff_keys = [key for key in artifacts if key.startswith("diffs/")]
    assert diff_keys
    patch = artifacts[diff_keys[0]].decode("utf-8")
    assert patch == expected_patch
    assert any(event.type == "file.diff" for event in normalized)


def test_snapshot_derived_diff_fixture() -> None:
    fixture = Path("tests/fixtures/diffs/snapshot/no_diff.jsonl")
    before = Path("tests/fixtures/diffs/snapshot/workspace_before")
    after = Path("tests/fixtures/diffs/snapshot/workspace_after")

    events = list(iter_events(fixture))
    normalized, artifacts = normalize_events(
        events,
        workspace_before=before,
        workspace_after=after,
    )

    diff_keys = [key for key in artifacts if key.startswith("diffs/")]
    assert diff_keys
    patch = artifacts[diff_keys[0]].decode("utf-8")
    assert "---" in patch
    assert "+++" in patch
    assert "@@" in patch
    assert any(event.type == "file.diff" for event in normalized)
