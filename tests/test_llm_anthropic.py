import json
from pathlib import Path

from flightlog.ingest.claude_code import iter_events
from flightlog.json_utils import canonical_json_dumps
from flightlog.llm.normalizers.anthropic import AnthropicNormalizer
from flightlog.llm.turn_builders.claude_code import build_turns


def test_anthropic_normalizer_maps_messages_and_tool_calls() -> None:
    normalizer = AnthropicNormalizer()
    turn = normalizer.normalize(
        raw_request={
            "model": "claude-3-7-sonnet",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "run tool"},
                        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"},
                    ],
                }
            ],
        },
        raw_response={
            "role": "assistant",
            "content": [
                {"type": "text", "text": "calling tool"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "tool.alpha",
                    "input": {"b": 2, "a": 1},
                },
            ],
            "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
        },
        meta={"session_id": "sess-1", "timestamp": "2026-01-01T00:00:00Z"},
    )

    assert turn.provider == "anthropic"
    assert turn.model == "claude-3-7-sonnet"
    assert turn.input_messages[0]["role"] == "user"
    assert turn.output_message is not None
    assert turn.output_message["role"] == "assistant"
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].name == "tool.alpha"
    assert turn.tool_calls[0].arguments_json == {"a": 1, "b": 2}
    assert turn.usage is not None
    assert turn.usage.total_tokens == 12


def test_claude_turn_builder_maps_tool_use_and_tool_result() -> None:
    fixture = Path("tests/fixtures/claude_code/claude_tool_use_session.jsonl")
    rows = []
    for line_no, line in enumerate(fixture.read_text(encoding="utf-8").splitlines(), start=1):
        rows.append((line_no, json.loads(line)))

    turns = build_turns(rows, default_session="fallback-s", default_run="fallback-r")
    assert len(turns) == 1
    turn = turns[0].turn
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].name == "tool.alpha"
    assert turn.tool_calls[0].arguments_json == {"a": 1, "b": 2}
    assert turn.input_messages
    assert turn.input_messages[0]["role"] == "user"
    assert turn.output_message is not None
    assert turn.output_message["role"] == "assistant"


def test_claude_ingest_ordering_is_deterministic() -> None:
    fixture = Path("tests/fixtures/claude_code/claude_tool_use_session.jsonl")
    first = [canonical_json_dumps(event.to_dict()) for event in iter_events(fixture)]
    second = [canonical_json_dumps(event.to_dict()) for event in iter_events(fixture)]
    assert first == second
