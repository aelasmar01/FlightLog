import json
from pathlib import Path

from flightlog.json_utils import canonical_json_dumps
from flightlog.llm.normalizers.openai_compat import OpenAICompatNormalizer
from flightlog.llm.normalizers.select import select_normalizer
from flightlog.llm.to_events import to_events


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_openai_compat_normalize_matches_expected_turn() -> None:
    fixture_dir = Path("tests/fixtures/llm/openai_compat")
    raw_request = _read_json(fixture_dir / "request.json")
    raw_response = _read_json(fixture_dir / "response.json")
    expected_turn = _read_json(fixture_dir / "expected_turn.json")

    normalizer = OpenAICompatNormalizer()
    turn = normalizer.normalize(
        raw_request=raw_request,
        raw_response=raw_response,
        meta={
            "provider": "openai_compat",
            "session_id": "openai-sess-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "url": "https://api.openai.com/v1/chat/completions",
            "status_code": 200,
            "latency_ms": 55.0,
            "streaming": False,
            "attempt": 1,
            "request_id": "req-openai-1",
        },
    )

    actual = turn.model_dump(mode="json", exclude_none=True)
    assert canonical_json_dumps(actual) == canonical_json_dumps(expected_turn)


def test_openai_compat_golden_events() -> None:
    fixture_dir = Path("tests/fixtures/llm/openai_compat")
    raw_request = _read_json(fixture_dir / "request.json")
    raw_response = _read_json(fixture_dir / "response.json")
    expected_lines = [
        line.strip()
        for line in (fixture_dir / "expected_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    normalizer = OpenAICompatNormalizer()
    turn = normalizer.normalize(
        raw_request=raw_request,
        raw_response=raw_response,
        meta={
            "provider": "openai_compat",
            "session_id": "openai-sess-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "url": "https://api.openai.com/v1/chat/completions",
            "status_code": 200,
            "latency_ms": 55.0,
            "streaming": False,
            "attempt": 1,
            "request_id": "req-openai-1",
        },
    )
    events = to_events(
        turn,
        run_id="openai-run-1",
        source="llm.normalized",
        emit_tool_call_events=True,
        event_namespace="openai-fixture",
    )
    actual_lines = [canonical_json_dumps(event.to_dict()) for event in events]
    assert actual_lines == expected_lines


def test_select_normalizer_for_openai_and_azure_style() -> None:
    normalizer = select_normalizer("openai_compat")
    assert isinstance(normalizer, OpenAICompatNormalizer)

    fixture_dir = Path("tests/fixtures/llm/openai_compat")
    raw_request = _read_json(fixture_dir / "request.json")
    raw_response = _read_json(fixture_dir / "response.json")
    turn = normalizer.normalize(
        raw_request=raw_request,
        raw_response=raw_response,
        meta={
            "provider": "openai_compat",
            "session_id": "azure-sess-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "url": "https://example.openai.azure.com/openai/deployments/demo/chat/completions",
            "status_code": 200,
        },
    )
    assert turn.provider == "openai_compat"
    assert turn.model == "gpt-4.1-mini"
