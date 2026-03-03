import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from typer.testing import CliRunner

from flightlog.cli import app
from flightlog.pack_writer import validate_pack


class _OpenAIHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > 0:
            self.rfile.read(content_length)
        response = {
            "id": "chatcmpl-sdk-1",
            "model": "gpt-4.1-mini",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
        }
        payload = json.dumps(response, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_sitecustomize_env_capture_and_pack_build(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OpenAIHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    capture_path = tmp_path / "sdk_capture.jsonl"
    repo_root = Path(__file__).resolve().parents[1]
    sitecustomize_dir = repo_root / "flightlog" / "llm" / "sdk_capture"

    script = (
        "import httpx\n"
        f"httpx.post('http://127.0.0.1:{server.server_address[1]}/v1/chat/completions', "
        "json={'model':'gpt-4.1-mini','messages':[{'role':'user','content':'ping'}]}, "
        "timeout=5)\n"
        "try:\n"
        "    httpx.post(\n"
        "        'https://api.anthropic.com.invalid/v1/messages',\n"
        "        json={\n"
        "            'model':'claude-3-7-sonnet',\n"
        "            'messages':[{'role':'user','content':'ping'}],\n"
        "        },\n"
        "        timeout=0.2,\n"
        "    )\n"
        "except Exception:\n"
        "    pass\n"
    )

    env = os.environ.copy()
    env["FLIGHTLOG"] = "1"
    env["FLIGHTLOG_OUT"] = str(capture_path)
    env["PYTHONPATH"] = f"{sitecustomize_dir}{os.pathsep}{repo_root}"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)

    assert completed.returncode == 0, completed.stderr
    lines = [line for line in capture_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 2

    records = [json.loads(line) for line in lines]
    providers = {record["provider_family"] for record in records}
    assert "openai_compat" in providers
    assert "anthropic" in providers

    runner = CliRunner()
    pack_dir = tmp_path / "sdk-pack"
    build = runner.invoke(
        app,
        ["pack", "build", "--input", str(capture_path), "--out", str(pack_dir)],
    )
    assert build.exit_code == 0, build.stdout
    ok, errors = validate_pack(pack_dir)
    assert ok, errors
