import json
from pathlib import Path

MODEL_FIXTURE_PATHS = (
    Path("tests/fixtures/claude_code/expected_timeline.jsonl"),
    Path("tests/fixtures/llm/turn/expected_timeline.jsonl"),
    Path("tests/fixtures/llm/openai_compat/expected_events.jsonl"),
    Path("tests/fixtures/http_capture/anthropic_capture.expected_timeline.jsonl"),
    Path("tests/fixtures/http_capture/openai_compat_capture.expected_timeline.jsonl"),
    Path("tests/fixtures/http_capture/gemini_capture.expected_timeline.jsonl"),
)

REQUEST_REQUIRED_KEYS = {
    "provider",
    "model",
    "messages",
    "tool_calls",
    "usage",
    "cost_usd",
    "raw_request_ref",
    "raw_response_ref",
}

RESPONSE_REQUIRED_KEYS = REQUEST_REQUIRED_KEYS | {"output_message"}


def test_model_event_payload_schema_contract() -> None:
    for path in MODEL_FIXTURE_PATHS:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for index, line in enumerate(lines, start=1):
            event = json.loads(line)
            event_type = event.get("type")
            if event_type not in {"model.request", "model.response"}:
                continue
            payload = event.get("payload")
            assert isinstance(payload, dict), f"{path}:{index} payload must be object"
            if event_type == "model.request":
                missing = sorted(REQUEST_REQUIRED_KEYS - set(payload.keys()))
            else:
                missing = sorted(RESPONSE_REQUIRED_KEYS - set(payload.keys()))
            assert not missing, f"{path}:{index} missing keys: {','.join(missing)}"
