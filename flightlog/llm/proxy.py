"""LLM reverse proxy capture for HTTP request/response pairs."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from urllib.parse import urlunsplit

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from flightlog.json_utils import canonical_json_dumps
from flightlog.llm.capture_record import (
    CaptureRecord,
    CaptureRequest,
    CaptureResponse,
    CaptureTransport,
)

ProviderFamily = Literal["anthropic", "openai_compat", "gemini"]


def _parse_listen(listen: str) -> tuple[str, int]:
    if ":" not in listen:
        raise ValueError("listen must be in '<host>:<port>' format")
    host, port_raw = listen.rsplit(":", maxsplit=1)
    if not host:
        raise ValueError("listen host cannot be empty")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("listen port must be an integer") from exc
    if port <= 0 or port > 65535:
        raise ValueError("listen port must be between 1 and 65535")
    return host, port


def _parse_json_bytes(payload: bytes) -> dict[str, Any] | None:
    if not payload:
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        return data
    return {"value": data}


def _session_id(headers: dict[str, str], timestamp: datetime) -> str:
    header_value = headers.get("x-flightlog-session-id")
    if header_value:
        return header_value
    return "proxy-" + timestamp.strftime("%Y%m%dT%H%M%S")


def _run_id(headers: dict[str, str], session_id: str, timestamp: datetime) -> str:
    header_value = headers.get("x-flightlog-run-id")
    if header_value:
        return header_value
    return f"{session_id}-run-{timestamp.strftime('%H%M%S%f')}"


@dataclass(slots=True)
class _CaptureWriter:
    output_path: Path
    lock: Lock

    def write(self, record: CaptureRecord) -> None:
        payload = canonical_json_dumps(record.model_dump(mode="json", exclude_none=True)) + "\n"
        with self.lock:
            with self.output_path.open("a", encoding="utf-8") as handle:
                handle.write(payload)


def create_proxy_app(
    *,
    upstream: str,
    output_path: Path,
    provider_family: ProviderFamily,
) -> Starlette:
    writer = _CaptureWriter(output_path=output_path, lock=Lock())
    upstream_base = upstream.rstrip("/")

    async def proxy_all(request: Request) -> Response:
        started = time.perf_counter()
        body_bytes = await request.body()
        request_headers = {
            key.lower(): value
            for key, value in request.headers.items()
            if key.lower() not in {"host", "content-length"}
        }
        query_string = request.url.query
        target_url = upstream_base + request.url.path
        if query_string:
            target_url = urlunsplit(("", "", target_url, query_string, ""))
        timestamp = datetime.now(UTC)
        session_id = _session_id(request_headers, timestamp)
        run_id = _run_id(request_headers, session_id, timestamp)
        request_json = _parse_json_bytes(body_bytes)

        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=60.0) as client:
                upstream_response = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=request_headers,
                    content=body_bytes if body_bytes else None,
                )
            response_bytes = upstream_response.content
            response_headers = dict(upstream_response.headers)
            status_code = upstream_response.status_code
            response_json = _parse_json_bytes(response_bytes)
            error_payload: dict[str, Any] | str | None = None
        except httpx.HTTPError as exc:
            response_bytes = str(exc).encode("utf-8")
            response_headers = {"content-type": "text/plain; charset=utf-8"}
            status_code = 599
            response_json = None
            error_payload = str(exc)

        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        streaming = response_headers.get("content-type", "").startswith("text/event-stream")
        record = CaptureRecord(
            ts=timestamp,
            session_id=session_id,
            run_id=run_id,
            provider_family=provider_family,
            request=CaptureRequest(
                method=request.method,
                url=target_url,
                headers=request_headers,
                json_body=request_json,
            ),
            response=CaptureResponse(
                status_code=status_code,
                headers=response_headers,
                json_body=response_json,
                error=error_payload,
            ),
            transport=CaptureTransport(
                latency_ms=latency_ms,
                streaming=streaming,
                attempt=1,
            ),
        )
        writer.write(record)

        passthrough_headers = {
            key: value
            for key, value in response_headers.items()
            if key.lower() not in {"transfer-encoding", "content-encoding", "connection"}
        }
        return Response(
            content=response_bytes,
            status_code=status_code,
            headers=passthrough_headers,
        )

    return Starlette(
        routes=[
            Route(
                "/{path:path}",
                proxy_all,
                methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            )
        ]
    )


def run_llm_proxy(
    *,
    listen: str,
    upstream: str,
    output_root: Path,
    provider_family: ProviderFamily,
) -> Path:
    host, port = _parse_listen(listen)
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / "capture.jsonl"
    app = create_proxy_app(
        upstream=upstream,
        output_path=output_path,
        provider_family=provider_family,
    )
    uvicorn.run(app, host=host, port=port, log_level="info")
    return output_path
