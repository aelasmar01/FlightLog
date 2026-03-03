from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from replaypack.cli import app
from replaypack.models import NormalizedEvent, RedactionReport
from replaypack.pack_writer import create_pack


def test_pack_validate_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    pack_dir = tmp_path / "pack"
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
    create_pack(pack_dir, events, {"a.txt": "x"}, RedactionReport())

    valid = runner.invoke(app, ["pack", "validate", "--path", str(pack_dir)])
    assert valid.exit_code == 0

    (pack_dir / "artifacts" / "a.txt").write_text("bad", encoding="utf-8")
    invalid = runner.invoke(app, ["pack", "validate", "--path", str(pack_dir)])
    assert invalid.exit_code == 1
