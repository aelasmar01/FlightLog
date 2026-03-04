"""HTTP proxy mode for MCP JSON-RPC traffic capture with streaming SSE support."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Literal
from urllib.parse import urljoin
from uuid import uuid4

import httpx

from flightlog.mcp.storage import append_message, transcript_path
from flightlog.mcp.utils import parse_jsonrpc_payload
from flightlog.redaction import load_redaction_config, redact_artifacts

# Optional OTel recorder — imported lazily to avoid hard dependency.
try:
    from flightlog.otel.span_export import SpanRecorder as _SpanRecorder
except ImportError:  # pragma: no cover
    _SpanRecorder = None  # type: ignore[assignment,misc]


def _is_sse(headers: httpx.Headers) -> bool:
    return "text/event-stream" in headers.get("content-type", "")


def _is_chunked(headers: httpx.Headers) -> bool:
    return "chunked" in headers.get("transfer-encoding", "")


class _CaptureProxyHandler(BaseHTTPRequestHandler):
    upstream: str
    transcript: Path
    redaction_config: dict[str, Any] | None
    span_recorder: Any | None  # Optional[SpanRecorder]
    server_name: str

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _capture(self, direction: Literal["client->server", "server->client"], body: bytes) -> None:
        text = body.decode("utf-8", errors="replace")
        if self.redaction_config is not None:
            redacted, _ = redact_artifacts({"body.json": text}, self.redaction_config)
            text = redacted.get("body.json", text.encode("utf-8")).decode("utf-8", errors="replace")
        for message in parse_jsonrpc_payload(direction, text):
            append_message(self.transcript, message)

    def _do_proxy_request(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b""
        self._capture("client->server", body)

        request_headers = {k: v for k, v in self.headers.items() if k.lower() != "host"}
        upstream_url = urljoin(self.upstream.rstrip("/") + "/", self.path.lstrip("/"))

        with httpx.Client().stream(
            self.command,
            upstream_url,
            headers=request_headers,
            content=body,
            timeout=30,
        ) as response:
            is_streaming = _is_sse(response.headers) or _is_chunked(response.headers)

            self.send_response(response.status_code)
            excluded = {"transfer-encoding", "connection", "content-length"}
            for key, value in response.headers.items():
                if key.lower() in excluded:
                    continue
                self.send_header(key, value)

            if is_streaming:
                # Do not send Content-Length; keep connection open while data flows.
                self.end_headers()
                captured: list[bytes] = []
                sse_buffer = b""

                try:
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        self.wfile.write(chunk)
                        try:
                            self.wfile.flush()
                        except BrokenPipeError:
                            break

                        if _is_sse(response.headers):
                            # Capture on SSE event boundaries (\n\n).
                            sse_buffer += chunk
                            while b"\n\n" in sse_buffer:
                                event, sse_buffer = sse_buffer.split(b"\n\n", 1)
                                captured.append(event + b"\n\n")
                        else:
                            captured.append(chunk)
                except httpx.ReadTimeout:
                    pass  # upstream closed; capture whatever arrived

                # Capture remaining buffer (partial SSE event or trailing data).
                if sse_buffer:
                    captured.append(sse_buffer)

                full_body = b"".join(captured)
                self._capture("server->client", full_body)
            else:
                content = response.read()
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                self._capture("server->client", content)

    def _proxy(self) -> None:
        recorder = getattr(self, "span_recorder", None)
        if recorder is not None:
            upstream_url = urljoin(self.upstream.rstrip("/") + "/", self.path.lstrip("/"))
            attrs: dict[str, Any] = {
                "http.method": self.command,
                "http.url": upstream_url,
                "mcp.server": getattr(self, "server_name", ""),
            }
            with recorder.span("mcp.request", kind="CLIENT", attributes=attrs):
                self._do_proxy_request()
        else:
            self._do_proxy_request()

    def do_GET(self) -> None:  # noqa: N802
        self._proxy()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()


def start_proxy_server(
    *,
    listen: str,
    upstream: str,
    name: str,
    output_root: Path,
    redaction_config_path: Path | None = None,
    span_recorder: Any | None = None,
) -> ThreadingHTTPServer:
    if ":" not in listen:
        raise ValueError("listen must be host:port")
    host, port_text = listen.rsplit(":", 1)
    port = int(port_text)

    session_id = str(uuid4())
    capture_path = transcript_path(output_root, name, session_id)
    if redaction_config_path:
        redaction_config = load_redaction_config(redaction_config_path)
    else:
        redaction_config = None

    handler = type(
        "CaptureProxyHandler",
        (_CaptureProxyHandler,),
        {
            "upstream": upstream,
            "transcript": capture_path,
            "redaction_config": redaction_config,
            "span_recorder": span_recorder,
            "server_name": name,
        },
    )
    return ThreadingHTTPServer((host, port), handler)


def run_proxy(
    *,
    listen: str,
    upstream: str,
    name: str,
    output_root: Path,
    redaction_config_path: Path | None = None,
    span_recorder: Any | None = None,
) -> None:
    server = start_proxy_server(
        listen=listen,
        upstream=upstream,
        name=name,
        output_root=output_root,
        redaction_config_path=redaction_config_path,
        span_recorder=span_recorder,
    )
    server.serve_forever()


def run_proxy_in_thread(
    *,
    listen: str,
    upstream: str,
    name: str,
    output_root: Path,
    redaction_config_path: Path | None = None,
    span_recorder: Any | None = None,
) -> tuple[ThreadingHTTPServer, Thread]:
    server = start_proxy_server(
        listen=listen,
        upstream=upstream,
        name=name,
        output_root=output_root,
        redaction_config_path=redaction_config_path,
        span_recorder=span_recorder,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
