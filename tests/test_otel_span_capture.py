"""Tests for OTel span capture via the MCP HTTP proxy."""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from flightlog.mcp.proxy_http import run_proxy_in_thread
from flightlog.otel.span_export import SpanRecorder


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _SimpleJsonHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"pong": True}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_span_recorder_writes_jsonl(tmp_path: Path) -> None:
    recorder = SpanRecorder(tmp_path)
    with recorder.span("test.op", kind="CLIENT", attributes={"key": "val"}) as ctx:
        ctx["status"] = "OK"

    spans_path = tmp_path / "otel" / "spans.jsonl"
    assert spans_path.exists()
    lines = spans_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    span = json.loads(lines[0])
    assert span["name"] == "test.op"
    assert span["kind"] == "CLIENT"
    assert span["status"] == "OK"
    assert span["attributes"] == {"key": "val"}
    assert "start_time_iso" in span
    assert "end_time_iso" in span
    assert span["duration_ms"] >= 0


def test_span_recorder_error_status(tmp_path: Path) -> None:
    recorder = SpanRecorder(tmp_path)
    try:
        with recorder.span("failing.op") as _ctx:
            raise ValueError("boom")
    except ValueError:
        pass

    spans = json.loads((tmp_path / "otel" / "spans.jsonl").read_text(encoding="utf-8").strip())
    assert spans["status"] == "ERROR"


def test_proxy_with_otel_writes_spans(tmp_path: Path) -> None:
    upstream_port = _free_port()
    upstream_server = HTTPServer(("127.0.0.1", upstream_port), _SimpleJsonHandler)
    threading.Thread(target=upstream_server.serve_forever, daemon=True).start()

    recorder = SpanRecorder(tmp_path)
    proxy_port = _free_port()
    proxy_server, _ = run_proxy_in_thread(
        listen=f"127.0.0.1:{proxy_port}",
        upstream=f"http://127.0.0.1:{upstream_port}",
        name="otel-test",
        output_root=tmp_path,
        span_recorder=recorder,
    )

    try:
        time.sleep(0.05)
        import urllib.request

        req_body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{proxy_port}/rpc",
            data=req_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        assert result.get("result") == {"pong": True}

        # Allow span to flush.
        time.sleep(0.05)

        spans_path = tmp_path / "otel" / "spans.jsonl"
        assert spans_path.exists(), "OTel spans file should be created"
        lines = spans_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1

        span = json.loads(lines[0])
        assert span["name"] == "mcp.request"
        assert span["kind"] == "CLIENT"
        assert span["attributes"].get("http.method") == "POST"
        assert span["attributes"].get("mcp.server") == "otel-test"
    finally:
        proxy_server.shutdown()
        upstream_server.shutdown()


def test_add_event_attaches_to_span(tmp_path: Path) -> None:
    recorder = SpanRecorder(tmp_path)
    with recorder.span("op.with.events") as ctx:
        recorder.add_event(ctx, "cache.hit", {"key": "abc"})
        recorder.add_event(ctx, "db.query", {"table": "users"})

    span = json.loads((tmp_path / "otel" / "spans.jsonl").read_text(encoding="utf-8").strip())
    assert len(span["events"]) == 2
    assert span["events"][0]["name"] == "cache.hit"
    assert span["events"][1]["name"] == "db.query"
