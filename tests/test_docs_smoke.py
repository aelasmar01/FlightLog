import json
import shutil
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from flightlog.cli import app


def test_docs_commands_smoke(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture = Path("tests/fixtures/claude_code/claude_session.jsonl").resolve()
    out_dir = tmp_path / "docs-pack"

    build = runner.invoke(
        app,
        ["pack", "build", "--input", str(fixture), "--out", str(out_dir)],
    )
    assert build.exit_code == 0, build.stdout

    validate = runner.invoke(app, ["pack", "validate", "--path", str(out_dir)])
    assert validate.exit_code == 0, validate.stdout

    diff_list = runner.invoke(app, ["pack", "diff", "--pack", str(out_dir), "--list"])
    assert diff_list.exit_code == 0, diff_list.stdout


def test_docs_mcp_wrap_stub_replay(tmp_path: Path) -> None:
    """End-to-end: mcp wrap -> stub generate -> replay run --offline."""
    repo_root = Path(__file__).resolve().parents[1]
    server_script = repo_root / "tests" / "fixtures" / "mcp" / "fake_stdio_server.py"
    runner = CliRunner()

    # Step 1: Wrap a stdio MCP server and capture a transcript.
    out_dir = tmp_path / "capture"
    request = '{"jsonrpc":"2.0","id":1,"method":"demo.echo","params":{"x":1}}\n'
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "flightlog.cli",
            "mcp",
            "wrap",
            "--name",
            "demo",
            "--out",
            str(out_dir),
            "--",
            sys.executable,
            str(server_script),
        ],
        input=request,
        text=True,
        capture_output=True,
        cwd=repo_root,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    transcripts = list((out_dir / "mcp" / "transcripts" / "demo").glob("*.jsonl"))
    assert len(transcripts) == 1, "Expected one transcript file from mcp wrap"
    transcript_path = transcripts[0]

    # Step 2: Generate a deterministic stub from the captured transcript.
    stub_out = tmp_path / "demo_stub.json"
    result = runner.invoke(
        app,
        [
            "mcp",
            "stub",
            "generate",
            "--transcript",
            str(transcript_path),
            "--out",
            str(stub_out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert stub_out.exists()

    # Step 3: Build a minimal replay pack containing a matching mcp.request event.
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    mcp_event = {
        "event_id": "evt-1",
        "ts": "2026-01-01T00:00:00+00:00",
        "source": "mcp_wire",
        "type": "mcp.request",
        "session_id": "s",
        "run_id": "r",
        "payload": {"server": "demo", "method": "demo.echo", "params": {"x": 1}},
    }
    (pack_dir / "timeline.jsonl").write_text(json.dumps(mcp_event) + "\n", encoding="utf-8")

    stub_dir = pack_dir / "mcp" / "stubs" / "demo"
    stub_dir.mkdir(parents=True)
    shutil.copy(stub_out, stub_dir / "session.json")

    # Step 4: Replay the pack offline against the generated stub.
    result = runner.invoke(app, ["replay", "run", "--pack", str(pack_dir), "--offline"])
    assert result.exit_code == 0, result.output
