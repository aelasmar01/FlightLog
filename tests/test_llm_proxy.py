import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import httpx
import uvicorn
from typer.testing import CliRunner

from flightlog.cli import app
from flightlog.llm.proxy import create_proxy_app
from flightlog.pack_writer import validate_pack


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _UpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > 0:
            self.rfile.read(content_length)

        response = {
            "id": "chatcmpl-proxy-1",
            "model": "gpt-4.1-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "ok",
                    },
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        payload = json.dumps(response, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start_upstream_server() -> tuple[ThreadingHTTPServer, Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _start_proxy_server(
    capture_path: Path,
    upstream_url: str,
) -> tuple[uvicorn.Server, Thread, int]:
    proxy_port = _free_port()
    proxy_app = create_proxy_app(
        upstream=upstream_url,
        output_path=capture_path,
        provider_family="openai_compat",
    )
    config = uvicorn.Config(proxy_app, host="127.0.0.1", port=proxy_port, log_level="error")
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("proxy server did not start in time")
        time.sleep(0.05)
    return server, thread, proxy_port


def _stop_proxy_server(server: uvicorn.Server, thread: Thread) -> None:
    server.should_exit = True
    thread.join(timeout=5)


def _load_capture_record(capture_path: Path) -> dict[str, Any]:
    deadline = time.time() + 5
    while time.time() < deadline:
        if capture_path.exists() and capture_path.stat().st_size > 0:
            break
        time.sleep(0.05)
    line = capture_path.read_text(encoding="utf-8").strip()
    return json.loads(line)


def test_llm_proxy_captures_openai_compatible_request_response(tmp_path: Path) -> None:
    upstream_server, upstream_thread = _start_upstream_server()
    upstream_port = int(upstream_server.server_address[1])
    capture_path = tmp_path / "capture.jsonl"
    proxy_server: uvicorn.Server | None = None
    proxy_thread: Thread | None = None
    try:
        proxy_server, proxy_thread, proxy_port = _start_proxy_server(
            capture_path=capture_path,
            upstream_url=f"http://127.0.0.1:{upstream_port}",
        )
        response = httpx.post(
            f"http://127.0.0.1:{proxy_port}/v1/chat/completions",
            json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "ping"}]},
            timeout=10,
        )
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "ok"

        record = _load_capture_record(capture_path)
        assert record["provider_family"] == "openai_compat"
        assert record["request"]["method"] == "POST"
        assert record["request"]["json_body"]["model"] == "gpt-4.1-mini"
        assert record["response"]["status_code"] == 200
        assert record["response"]["json_body"]["choices"][0]["message"]["role"] == "assistant"
    finally:
        if proxy_server is not None and proxy_thread is not None:
            _stop_proxy_server(proxy_server, proxy_thread)
        upstream_server.shutdown()
        upstream_server.server_close()
        upstream_thread.join(timeout=5)


def test_llm_proxy_capture_builds_valid_pack(tmp_path: Path) -> None:
    upstream_server, upstream_thread = _start_upstream_server()
    upstream_port = int(upstream_server.server_address[1])
    capture_path = tmp_path / "capture.jsonl"
    proxy_server: uvicorn.Server | None = None
    proxy_thread: Thread | None = None
    try:
        proxy_server, proxy_thread, proxy_port = _start_proxy_server(
            capture_path=capture_path,
            upstream_url=f"http://127.0.0.1:{upstream_port}",
        )
        response = httpx.post(
            f"http://127.0.0.1:{proxy_port}/v1/chat/completions",
            json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "ping"}]},
            timeout=10,
        )
        assert response.status_code == 200
    finally:
        if proxy_server is not None and proxy_thread is not None:
            _stop_proxy_server(proxy_server, proxy_thread)
        upstream_server.shutdown()
        upstream_server.server_close()
        upstream_thread.join(timeout=5)

    runner = CliRunner()
    out_dir = tmp_path / "proxy-pack"
    build = runner.invoke(
        app,
        ["pack", "build", "--input", str(capture_path), "--out", str(out_dir)],
    )
    assert build.exit_code == 0, build.stdout

    ok, errors = validate_pack(out_dir)
    assert ok, errors
