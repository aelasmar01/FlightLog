import json
import subprocess
import sys
from pathlib import Path

from replaypack.mcp.stubgen import params_hash


def test_stub_server_returns_stubbed_response(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]

    stub = {
        "schema_version": "1",
        "generated_at": "2026-01-01T00:00:00Z",
        "server_name": "demo",
        "methods": {"demo.method": {params_hash({"x": 1}): {"result": {"ok": True}}}},
        "fallback_rules": [],
    }
    stub_path = tmp_path / "stub.json"
    stub_path.write_text(json.dumps(stub), encoding="utf-8")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "replaypack.cli",
            "mcp",
            "stub",
            "serve",
            "--stub",
            str(stub_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=repo_root,
    )

    assert proc.stdin is not None
    assert proc.stdout is not None

    req = {"jsonrpc": "2.0", "id": 1, "method": "demo.method", "params": {"x": 1}}
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()

    line = proc.stdout.readline().strip()
    response = json.loads(line)
    assert response["result"]["ok"] is True

    proc.stdin.close()
    proc.wait(timeout=5)
