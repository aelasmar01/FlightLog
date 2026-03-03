from pathlib import Path

from flightlog.ingest.claude_code import detect, extract_artifacts, iter_events
from flightlog.json_utils import canonical_json_dumps


def test_claude_ingest_golden() -> None:
    fixture = Path("tests/fixtures/claude_code/claude_session.jsonl")
    expected = Path("tests/fixtures/claude_code/expected_timeline.jsonl")

    assert detect(fixture)
    events = list(iter_events(fixture))
    actual_lines = [canonical_json_dumps(event.to_dict()) for event in events]
    expected_lines = [
        line.strip() for line in expected.read_text(encoding="utf-8").splitlines() if line.strip()
    ]

    assert actual_lines == expected_lines


def test_claude_extract_artifacts() -> None:
    fixture = Path("tests/fixtures/claude_code/claude_session.jsonl")
    artifacts = extract_artifacts(fixture)
    assert any(key.endswith("_prompt.txt") for key in artifacts)
    assert any(key.endswith("_tool_output.txt") for key in artifacts)


def test_claude_no_duplicate_tool_call_events() -> None:
    fixture = Path("tests/fixtures/claude_code/claude_tool_use_session.jsonl")
    events = list(iter_events(fixture))
    tool_call_events = [event for event in events if event.type == "tool.call"]
    assert len(tool_call_events) == 1

    model_responses = [event for event in events if event.type == "model.response"]
    assert len(model_responses) == 1
    assert model_responses[0].payload.get("tool_calls") == [
        {"id": "toolu_1", "index": 1, "name": "tool.alpha", "arguments_json": {"a": 1, "b": 2}}
    ]
