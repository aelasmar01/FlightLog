import json
import threading
import time
from pathlib import Path

from flightlog.pack_writer import validate_pack
from flightlog.watch import watch_input


def test_watch_emits_appended_events(tmp_path: Path) -> None:
    input_path = tmp_path / "session.jsonl"
    initial = {
        "ts": "2026-01-01T00:00:00Z",
        "source": "claude_code",
        "type": "model_request",
        "session_id": "s1",
        "run_id": "r1",
        "prompt": "hello",
    }
    input_path.write_text(json.dumps(initial) + "\n", encoding="utf-8")

    emitted: list[str] = []

    thread = threading.Thread(
        target=lambda: watch_input(
            input_path=input_path,
            emit=emitted.append,
            out_dir=None,
            redaction_path=None,
            poll_interval_seconds=0.05,
            max_events=1,
            idle_timeout_seconds=3.0,
            from_start=False,
        ),
        daemon=True,
    )
    thread.start()

    time.sleep(0.2)
    appended = {
        "ts": "2026-01-01T00:00:01Z",
        "source": "claude_code",
        "type": "tool_result",
        "session_id": "s1",
        "run_id": "r1",
        "tool_output": "ok",
    }
    with input_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(appended) + "\n")

    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(emitted) == 1

    event = json.loads(emitted[0])
    assert event["type"] == "tool.result"


def test_watch_updates_pack_without_corruption(tmp_path: Path) -> None:
    input_path = tmp_path / "session.jsonl"
    out_dir = tmp_path / "watch-pack"

    first = {
        "ts": "2026-01-01T00:00:00Z",
        "source": "claude_code",
        "type": "model_request",
        "session_id": "s1",
        "run_id": "r1",
        "prompt": "first",
    }
    input_path.write_text(json.dumps(first) + "\n", encoding="utf-8")

    emitted: list[str] = []

    thread = threading.Thread(
        target=lambda: watch_input(
            input_path=input_path,
            emit=emitted.append,
            out_dir=out_dir,
            redaction_path=None,
            poll_interval_seconds=0.05,
            max_events=2,
            idle_timeout_seconds=3.0,
            from_start=True,
        ),
        daemon=True,
    )
    thread.start()

    time.sleep(0.2)
    second = {
        "ts": "2026-01-01T00:00:01Z",
        "source": "claude_code",
        "type": "model_response",
        "session_id": "s1",
        "run_id": "r1",
        "response": "second",
    }
    with input_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(second) + "\n")

    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(emitted) == 2

    ok, errors = validate_pack(out_dir)
    assert ok, errors
    timeline_lines = (out_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
    assert len([line for line in timeline_lines if line.strip()]) >= 2
