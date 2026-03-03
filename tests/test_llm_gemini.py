import json
from pathlib import Path

from flightlog.llm.normalizers.gemini import GeminiNormalizer


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_gemini_function_call_maps_to_tool_call_with_canonical_arguments() -> None:
    fixture_dir = Path("tests/fixtures/llm/gemini")
    raw_request = _read_json(fixture_dir / "request.json")
    raw_response = _read_json(fixture_dir / "response.json")

    normalizer = GeminiNormalizer()
    turn = normalizer.normalize(
        raw_request=raw_request,
        raw_response=raw_response,
        meta={
            "provider": "gemini",
            "session_id": "gemini-sess-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent",
            "status_code": 200,
        },
    )

    assert turn.provider == "gemini"
    assert turn.model == "gemini-2.0-flash"
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].name == "tool.alpha"
    assert turn.tool_calls[0].arguments_json == {"a": 1, "b": 2}
    assert turn.output_message is not None
    assert turn.output_message["role"] == "assistant"
    assert turn.usage is not None
    assert turn.usage.total_tokens == 21
