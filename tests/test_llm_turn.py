from datetime import UTC, datetime
from pathlib import Path

from flightlog.json_utils import canonical_json_dumps
from flightlog.llm.message_schema import canonicalize_message
from flightlog.llm.models import LLMTurn, ToolCall, TransportMeta, Usage
from flightlog.llm.serialization import dumps_turn, loads_turn
from flightlog.llm.to_events import to_events


def test_llm_turn_round_trip_serialization() -> None:
    turn = LLMTurn(
        provider="anthropic",
        model="claude-3-7-sonnet",
        session_id="sess-1",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        input_messages=[{"role": "user", "content": "hello"}],
        output_message={"role": "assistant", "content": "world"},
        tool_calls=[ToolCall(id="call_1", name="tool.alpha", arguments_json={"x": 1}, index=0)],
        usage=Usage(input_tokens=10, output_tokens=12, total_tokens=22),
        cost_usd=0.001,
        transport=TransportMeta(
            url="https://api.example.com/v1/messages",
            status_code=200,
            latency_ms=32.1,
            streaming=False,
            attempt=1,
            request_id="req-1",
        ),
    )

    encoded = dumps_turn(turn)
    decoded = loads_turn(encoded)
    assert decoded.model_dump(mode="json", exclude_none=True) == turn.model_dump(
        mode="json", exclude_none=True
    )


def test_message_canonicalization_is_stable_for_key_order() -> None:
    first = canonicalize_message(
        {
            "role": "assistant",
            "content": {"b": 2, "a": 1},
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "tool.alpha", "arguments": {"z": 2, "a": 1}},
                }
            ],
        }
    )
    second = canonicalize_message(
        {
            "tool_calls": [
                {
                    "function": {"arguments": {"a": 1, "z": 2}, "name": "tool.alpha"},
                    "id": "call_1",
                }
            ],
            "content": {"a": 1, "b": 2},
            "role": "assistant",
        }
    )
    assert canonical_json_dumps(first) == canonical_json_dumps(second)


def test_to_events_golden_fixture() -> None:
    fixture_dir = Path("tests/fixtures/llm/turn")
    turn = loads_turn((fixture_dir / "sample_turn.json").read_text(encoding="utf-8"))
    events = to_events(
        turn,
        run_id="turn-run-1",
        source="llm.normalized",
        emit_tool_call_events=True,
    )
    actual_lines = [canonical_json_dumps(event.to_dict()) for event in events]
    expected_lines = [
        line.strip()
        for line in (fixture_dir / "expected_timeline.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert actual_lines == expected_lines
