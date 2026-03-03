from pathlib import Path

from replaypack.mcp.models import McpTranscript
from replaypack.mcp.storage import iter_messages
from replaypack.mcp.stubgen import generate_stub, params_hash


def test_stub_generation_from_fixture() -> None:
    transcript = Path("tests/fixtures/mcp/transcript.jsonl")
    messages = list(iter_messages(transcript))

    stub = generate_stub(messages, server_name="demo")

    methods = stub["methods"]
    assert set(methods.keys()) == {"tool.alpha", "tool.beta"}
    assert len(methods["tool.alpha"]) == 2
    assert len(methods["tool.beta"]) == 1


def test_params_hash_canonical_ordering() -> None:
    assert params_hash({"a": 1, "b": 2}) == params_hash({"b": 2, "a": 1})


def test_transcript_model_round_trip() -> None:
    transcript = McpTranscript(server_name="demo", session_id="s1")
    message = list(iter_messages(Path("tests/fixtures/mcp/transcript.jsonl")))[0]
    transcript.append(message)
    encoded = transcript.model_dump(mode="json")
    decoded = McpTranscript.model_validate(encoded)
    assert decoded.model_dump(mode="json") == encoded
