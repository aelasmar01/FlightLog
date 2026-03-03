import json
from datetime import UTC, datetime
from pathlib import Path

from flightlog.mcp.stubgen import params_hash
from flightlog.replay_runner import run_replay


def test_replay_runner_offline_success(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir(parents=True)

    timeline_event = {
        "event_id": "evt-1",
        "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "source": "mcp_wire",
        "type": "mcp.request",
        "session_id": "s",
        "run_id": "r",
        "payload": {
            "server": "demo",
            "method": "demo.method",
            "params": {"x": 1},
        },
    }
    (pack_dir / "timeline.jsonl").write_text(json.dumps(timeline_event) + "\n", encoding="utf-8")

    stub_dir = pack_dir / "mcp" / "stubs" / "demo"
    stub_dir.mkdir(parents=True)
    stub = {"methods": {"demo.method": {params_hash({"x": 1}): {"result": {"ok": True}}}}}
    (stub_dir / "session.json").write_text(json.dumps(stub), encoding="utf-8")

    ok, mismatches, events = run_replay(pack_dir, offline=True)
    assert ok
    assert mismatches == []
    assert events == 1


def test_replay_runner_offline_mismatch(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir(parents=True)

    timeline_event = {
        "event_id": "evt-1",
        "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "source": "mcp_wire",
        "type": "mcp.request",
        "session_id": "s",
        "run_id": "r",
        "payload": {
            "server": "demo",
            "method": "missing.method",
            "params": {},
        },
    }
    (pack_dir / "timeline.jsonl").write_text(json.dumps(timeline_event) + "\n", encoding="utf-8")

    stub_dir = pack_dir / "mcp" / "stubs" / "demo"
    stub_dir.mkdir(parents=True)
    (stub_dir / "session.json").write_text(json.dumps({"methods": {}}), encoding="utf-8")

    ok, mismatches, _ = run_replay(pack_dir, offline=True)
    assert not ok
    assert mismatches
