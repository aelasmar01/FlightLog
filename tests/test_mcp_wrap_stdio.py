import subprocess
import sys
from pathlib import Path


def test_mcp_wrap_captures_stdio_transcript(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    server_script = repo_root / "tests" / "fixtures" / "mcp" / "fake_stdio_server.py"

    cmd = [
        sys.executable,
        "-m",
        "flightlog.cli",
        "mcp",
        "wrap",
        "--name",
        "fake",
        "--out",
        str(tmp_path),
        "--",
        sys.executable,
        str(server_script),
    ]

    request = '{"jsonrpc":"2.0","id":1,"method":"demo.echo","params":{"x":1}}\n'
    completed = subprocess.run(
        cmd,
        input=request,
        text=True,
        capture_output=True,
        cwd=repo_root,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

    transcript_dir = tmp_path / "mcp" / "transcripts" / "fake"
    transcripts = list(transcript_dir.glob("*.jsonl"))
    assert len(transcripts) == 1

    content = transcripts[0].read_text(encoding="utf-8")
    assert '"kind":"request"' in content
    assert '"kind":"response"' in content
