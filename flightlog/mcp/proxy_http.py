"""HTTP proxy mode for MCP JSON-RPC traffic capture."""

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


class _CaptureProxyHandler(BaseHTTPRequestHandler):
    upstream: str
    transcript: Path
    redaction_config: dict[str, Any] | None

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _capture(self, direction: Literal["client->server", "server->client"], body: bytes) -> None:
        text = body.decode("utf-8", errors="replace")
        if self.redaction_config is not None:
            redacted, _ = redact_artifacts({"body.json": text}, self.redaction_config)
            text = redacted.get("body.json", text.encode("utf-8")).decode("utf-8", errors="replace")
        for message in parse_jsonrpc_payload(direction, text):
            append_message(self.transcript, message)

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b""
        self._capture("client->server", body)

        request_headers = {k: v for k, v in self.headers.items() if k.lower() != "host"}
        upstream_url = urljoin(self.upstream.rstrip("/") + "/", self.path.lstrip("/"))

        response = httpx.request(
            self.command,
            upstream_url,
            headers=request_headers,
            content=body,
            timeout=30,
        )
        response.read()

        self._capture("server->client", response.content)

        self.send_response(response.status_code)
        excluded = {"transfer-encoding", "connection", "content-length"}
        for key, value in response.headers.items():
            if key.lower() in excluded:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        self.wfile.write(response.content)

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
) -> None:
    server = start_proxy_server(
        listen=listen,
        upstream=upstream,
        name=name,
        output_root=output_root,
        redaction_config_path=redaction_config_path,
    )
    server.serve_forever()


def run_proxy_in_thread(
    *,
    listen: str,
    upstream: str,
    name: str,
    output_root: Path,
    redaction_config_path: Path | None = None,
) -> tuple[ThreadingHTTPServer, Thread]:
    server = start_proxy_server(
        listen=listen,
        upstream=upstream,
        name=name,
        output_root=output_root,
        redaction_config_path=redaction_config_path,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
