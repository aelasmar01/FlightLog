import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from flightlog.audit_export import export_audit
from flightlog.cli import app
from flightlog.models import NormalizedEvent, RedactionReport
from flightlog.pack_writer import create_pack


def _event(event_id: str, event_type: str, payload: dict[str, object]) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        source="test",
        type=event_type,
        session_id="s",
        run_id="r",
        payload=payload,
    )


def test_export_audit_is_deterministic(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    events = [
        _event("e1", "tool.call", {"tool": "shell"}),
        _event("e2", "mcp.request", {"method": "tool.alpha", "params": {}}),
    ]
    create_pack(pack_dir, events, {}, RedactionReport())

    config = tmp_path / "audit.yml"
    config.write_text(
        "owner: qa\npurpose: test\ndata_categories:\n  - prompts\nretention: 30d\n",
        encoding="utf-8",
    )

    out1 = tmp_path / "audit1.json"
    out2 = tmp_path / "audit2.json"
    csv_out = tmp_path / "audit.csv"

    export_audit(pack_path=pack_dir, out_json=out1, out_csv=csv_out, config_path=config)
    export_audit(pack_path=pack_dir, out_json=out2, out_csv=None, config_path=config)

    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    data = json.loads(out1.read_text(encoding="utf-8"))
    assert data["events"]["counts_by_type"]["mcp.request"] == 1
    assert data["events"]["tool_names"] == ["shell"]
    assert data["governance"]["owner"] == "qa"

    csv_text = csv_out.read_text(encoding="utf-8")
    assert csv_text.startswith("section,name,value")


def test_export_audit_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    pack_dir = tmp_path / "pack"
    create_pack(
        pack_dir,
        [_event("e1", "model.request", {"text": "x"})],
        {},
        RedactionReport(),
    )

    out = tmp_path / "audit.json"
    result = runner.invoke(
        app,
        ["export", "audit", "--pack", str(pack_dir), "--out", str(out)],
    )
    assert result.exit_code == 0
    assert out.exists()
