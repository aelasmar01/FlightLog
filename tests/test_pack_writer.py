import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

from replaypack.models import NormalizedEvent, RedactionReport
from replaypack.pack_writer import create_pack


def _build_events() -> list[NormalizedEvent]:
    return [
        NormalizedEvent(
            event_id="evt-1",
            ts=datetime(2026, 1, 1, tzinfo=UTC),
            source="test",
            type="model.request",
            session_id="s1",
            run_id="r1",
            payload={"msg": "hello"},
        ),
        NormalizedEvent(
            event_id="evt-2",
            ts=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
            source="test",
            type="model.response",
            session_id="s1",
            run_id="r1",
            payload={"msg": "world"},
        ),
    ]


def test_create_pack_and_zip(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    events = _build_events()
    artifacts = {"one.txt": "artifact-data"}
    report = RedactionReport()

    create_pack(pack_dir, events, artifacts, report)

    assert (pack_dir / "manifest.json").exists()
    assert (pack_dir / "timeline.jsonl").exists()
    assert (pack_dir / "artifacts").exists()

    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "timeline_sha256" in manifest
    assert manifest["artifacts"]["artifacts/one.txt"]

    zip_path = tmp_path / "pack.zip"
    create_pack(zip_path, events, artifacts, report, zip_output=True)
    assert zip_path.exists()

    with ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "timeline.jsonl" in names
        assert "artifacts/one.txt" in names
