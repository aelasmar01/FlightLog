"""HTTP transport recorder for MCP servers — wrap-like semantics over the HTTP proxy."""

from __future__ import annotations

from pathlib import Path
from threading import Thread
from typing import Any

from flightlog.mcp.proxy_http import start_proxy_server


def run_wrap_http(
    *,
    name: str,
    listen: str,
    upstream: str,
    output_root: Path,
    redaction_config_path: Path | None = None,
) -> tuple[Any, Path]:
    """Start an HTTP recorder for an MCP server and return the server + transcript path.

    Unlike ``run_proxy`` (which blocks forever), this function returns immediately
    after starting the server in a background thread.  Callers are responsible for
    shutting the server down.

    Args:
        name: MCP server name used for transcript path naming.
        listen: ``"host:port"`` address to listen on.
        upstream: Upstream MCP server URL, e.g. ``"http://localhost:8080"``.
        output_root: Root directory for transcript output.
        redaction_config_path: Optional path to a ``redaction.yml``-style config.

    Returns:
        A 2-tuple of ``(server, transcript_path)`` where *server* is a
        :class:`~http.server.ThreadingHTTPServer` instance.
    """
    server = start_proxy_server(
        listen=listen,
        upstream=upstream,
        name=name,
        output_root=output_root,
        redaction_config_path=redaction_config_path,
    )
    # The transcript path is constructed using the same session_id that
    # start_proxy_server used internally.  We re-derive it by peeking at the
    # handler class attributes set by start_proxy_server.
    handler_class = server.RequestHandlerClass
    capture_path: Path = getattr(handler_class, "transcript", output_root / "unknown.jsonl")

    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, capture_path


def run_wrap_http_blocking(
    *,
    name: str,
    listen: str,
    upstream: str,
    output_root: Path,
    redaction_config_path: Path | None = None,
) -> None:
    """Start an HTTP recorder and block until interrupted."""
    server = start_proxy_server(
        listen=listen,
        upstream=upstream,
        name=name,
        output_root=output_root,
        redaction_config_path=redaction_config_path,
    )
    server.serve_forever()
