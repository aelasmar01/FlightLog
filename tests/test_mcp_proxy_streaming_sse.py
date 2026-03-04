"""Tests for SSE/chunked streaming support in the MCP HTTP proxy."""

from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from flightlog.mcp.proxy_http import run_proxy_in_thread
from flightlog.mcp.storage import iter_messages


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _SseUpstreamHandler(BaseHTTPRequestHandler):
    """Minimal SSE upstream: emits 3 events then closes."""

    # Force HTTP/1.0 so the connection is closed after the response body.
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        import json

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for i in range(3):
            payload = json.dumps(
                {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"step": i}}
            )
            line = f"data: {payload}\n\n".encode()
            self.wfile.write(line)
            self.wfile.flush()
            time.sleep(0.02)


def _start_sse_upstream() -> tuple[HTTPServer, int]:
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _SseUpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_proxy_sse_streams_and_captures_events(tmp_path: Path) -> None:
    upstream_server, upstream_port = _start_sse_upstream()
    proxy_port = _free_port()

    proxy_server, _ = run_proxy_in_thread(
        listen=f"127.0.0.1:{proxy_port}",
        upstream=f"http://127.0.0.1:{upstream_port}",
        name="sse-test",
        output_root=tmp_path,
    )

    try:
        # Allow proxy to start.
        time.sleep(0.05)

        # Collect SSE chunks from the proxy as they arrive.
        import urllib.request

        received: list[str] = []
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{proxy_port}/events", timeout=5) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")
                    if line:
                        received.append(line)
        except Exception:
            pass  # Connection closed after 3 events — that's expected.

        # Client should have received 3 SSE data lines.
        data_lines = [line for line in received if line.startswith("data:")]
        assert len(data_lines) == 3, f"Expected 3 data lines, got: {received}"
        assert '"step": 0' in data_lines[0] or '"step":0' in data_lines[0]
        assert '"step": 1' in data_lines[1] or '"step":1' in data_lines[1]
        assert '"step": 2' in data_lines[2] or '"step":2' in data_lines[2]

        # Allow transcript to flush.
        time.sleep(0.05)

        # Transcript should exist with at least the captured server response.
        transcript_dir = tmp_path / "mcp" / "transcripts" / "sse-test"
        transcripts = list(transcript_dir.glob("*.jsonl"))
        assert len(transcripts) == 1, f"Expected 1 transcript, found: {transcripts}"

        messages = list(iter_messages(transcripts[0]))
        server_messages = [m for m in messages if m.direction == "server->client"]
        assert len(server_messages) >= 1
        assert transcripts[0].stat().st_size > 0

    finally:
        proxy_server.shutdown()
        upstream_server.shutdown()


def test_proxy_non_streaming_still_works(tmp_path: Path) -> None:
    """Regression: regular JSON responses still captured correctly."""
    import json

    class _JsonHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    upstream_port = _free_port()
    upstream_server = HTTPServer(("127.0.0.1", upstream_port), _JsonHandler)
    thread = threading.Thread(target=upstream_server.serve_forever, daemon=True)
    thread.start()

    proxy_port = _free_port()
    proxy_server, _ = run_proxy_in_thread(
        listen=f"127.0.0.1:{proxy_port}",
        upstream=f"http://127.0.0.1:{upstream_port}",
        name="json-test",
        output_root=tmp_path,
    )

    try:
        time.sleep(0.05)
        import urllib.request

        request_body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "demo", "params": {}}
        ).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{proxy_port}/rpc",
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        assert result.get("result") == {"ok": True}

        time.sleep(0.05)
        transcript_dir = tmp_path / "mcp" / "transcripts" / "json-test"
        transcripts = list(transcript_dir.glob("*.jsonl"))
        assert len(transcripts) == 1
        messages = list(iter_messages(transcripts[0]))
        assert any(m.direction == "client->server" for m in messages)
        assert any(m.direction == "server->client" for m in messages)
    finally:
        proxy_server.shutdown()
        upstream_server.shutdown()
