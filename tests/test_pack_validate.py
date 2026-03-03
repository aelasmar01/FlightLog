from datetime import UTC, datetime
from pathlib import Path

from flightlog.models import NormalizedEvent, RedactionReport
from flightlog.pack_writer import create_pack, validate_pack


def test_validate_detects_corruption(tmp_path: Path) -> None:
    events = [
        NormalizedEvent(
            event_id="evt-1",
            ts=datetime(2026, 1, 1, tzinfo=UTC),
            source="test",
            type="model.request",
            session_id="s",
            run_id="r",
            payload={"x": 1},
        )
    ]

    pack_dir = tmp_path / "pack"
    create_pack(pack_dir, events, {"x.txt": "hello"}, RedactionReport())
    ok, errors = validate_pack(pack_dir)
    assert ok
    assert not errors

    artifact = pack_dir / "artifacts" / "x.txt"
    artifact.write_text("tampered", encoding="utf-8")

    ok2, errors2 = validate_pack(pack_dir)
    assert not ok2
    assert any("hash mismatch" in error for error in errors2)


def test_validate_fails_on_missing_manifest(tmp_path: Path) -> None:
    pack_dir = tmp_path / "missing_manifest"
    pack_dir.mkdir()
    (pack_dir / "timeline.jsonl").write_text("{}\n", encoding="utf-8")
    ok, errors = validate_pack(pack_dir)
    assert not ok
    assert errors == ["manifest.json missing"]
