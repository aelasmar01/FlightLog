import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx

from flightlog.mcp.proxy_http import run_proxy_in_thread


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _UpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        request = json.loads(body.decode("utf-8"))
        response = {"jsonrpc": "2.0", "id": request.get("id"), "result": {"ok": True}}
        payload = json.dumps(response).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_http_proxy_captures_transcript(tmp_path: Path) -> None:
    upstream_port = _free_port()
    upstream = ThreadingHTTPServer(("127.0.0.1", upstream_port), _UpstreamHandler)
    upstream_thread = Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    proxy_port = _free_port()
    server, thread = run_proxy_in_thread(
        listen=f"127.0.0.1:{proxy_port}",
        upstream=f"http://127.0.0.1:{upstream_port}",
        name="http_demo",
        output_root=tmp_path,
    )

    try:
        response = httpx.post(
            f"http://127.0.0.1:{proxy_port}/rpc",
            json={"jsonrpc": "2.0", "id": 7, "method": "ping", "params": {}},
            timeout=5.0,
        )
        assert response.status_code == 200
        assert response.json()["result"]["ok"] is True
    finally:
        server.shutdown()
        thread.join(timeout=2.0)
        upstream.shutdown()
        upstream_thread.join(timeout=2.0)

    transcript_dir = tmp_path / "mcp" / "transcripts" / "http_demo"
    transcripts = list(transcript_dir.glob("*.jsonl"))
    assert len(transcripts) == 1

    content = transcripts[0].read_text(encoding="utf-8")
    assert '"kind":"request"' in content
    assert '"kind":"response"' in content
