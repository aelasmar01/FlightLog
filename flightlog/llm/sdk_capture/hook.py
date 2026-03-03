"""HTTPX monkeypatch capture hook used by SDK-level env instrumentation."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal, cast

import httpx

from flightlog.json_utils import canonical_json_dumps
from flightlog.llm.capture_record import (
    CaptureRecord,
    CaptureRequest,
    CaptureResponse,
    CaptureTransport,
)

ProviderFamily = Literal["anthropic", "openai_compat", "gemini"]

_PATCH_LOCK = Lock()
_WRITE_LOCK = Lock()
_PATCHED = False
_ORIGINAL_SYNC_REQUEST: Callable[..., httpx.Response] | None = None
_ORIGINAL_ASYNC_REQUEST: Callable[..., Awaitable[httpx.Response]] | None = None


def _env_truthy(name: str) -> bool:
    value = os.getenv(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _capture_path() -> Path:
    out_value = os.getenv("FLIGHTLOG_OUT", "/tmp/flightlog-sdk-capture")
    out_path = Path(out_value)
    if out_path.suffix == ".jsonl":
        capture_path = out_path
    else:
        capture_path = out_path / "capture.jsonl"
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    return capture_path


def _session_id(timestamp: datetime) -> str:
    value = os.getenv("FLIGHTLOG_SESSION_ID")
    if value:
        return value
    return "sdk-" + timestamp.strftime("%Y%m%dT%H%M%S")


def _run_id(session_id: str, timestamp: datetime) -> str:
    value = os.getenv("FLIGHTLOG_RUN_ID")
    if value:
        return value
    return f"{session_id}-run-{timestamp.strftime('%H%M%S%f')}"


def _provider_family(url: str) -> ProviderFamily:
    normalized = url.lower()
    if "anthropic.com" in normalized:
        return "anthropic"
    if "generativelanguage.googleapis.com" in normalized or "googleapis.com" in normalized:
        return "gemini"
    return "openai_compat"


def _request_json(kwargs: dict[str, Any]) -> dict[str, Any] | None:
    json_value = kwargs.get("json")
    if isinstance(json_value, Mapping):
        return dict(json_value)
    if json_value is not None:
        return {"value": json_value}

    content = kwargs.get("content")
    if isinstance(content, bytes):
        try:
            parsed = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(parsed, Mapping):
            return dict(parsed)
        return {"value": parsed}
    return None


def _normalized_headers(value: Any) -> dict[str, str]:
    pairs: list[tuple[str, str]] = []
    if value is None:
        return {}
    if isinstance(value, Mapping):
        for key, item_value in value.items():
            pairs.append((str(key), str(item_value)))
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            pairs.append((str(item[0]), str(item[1])))
    else:
        return {}
    return {key.lower(): item_value for key, item_value in pairs}


def _response_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        parsed = response.json()
    except (ValueError, json.JSONDecodeError):
        return None
    if isinstance(parsed, Mapping):
        return dict(parsed)
    return {"value": parsed}


def _write_record(record: CaptureRecord) -> None:
    payload = canonical_json_dumps(record.model_dump(mode="json", exclude_none=True)) + "\n"
    path = _capture_path()
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload)


def _build_record(
    *,
    timestamp: datetime,
    method: str,
    url: str,
    request_headers: dict[str, str],
    request_json: dict[str, Any] | None,
    status_code: int,
    response_headers: dict[str, str],
    response_json: dict[str, Any] | None,
    error: str | None,
    latency_ms: float,
) -> CaptureRecord:
    session_id = _session_id(timestamp)
    run_id = _run_id(session_id, timestamp)
    provider_family = _provider_family(url)
    return CaptureRecord(
        ts=timestamp,
        session_id=session_id,
        run_id=run_id,
        provider_family=provider_family,
        request=CaptureRequest(
            method=method,
            url=url,
            headers=request_headers,
            json_body=request_json,
        ),
        response=CaptureResponse(
            status_code=status_code,
            headers=response_headers,
            json_body=response_json,
            error=error,
        ),
        transport=CaptureTransport(
            latency_ms=round(latency_ms, 3),
            streaming=response_headers.get("content-type", "").startswith("text/event-stream"),
            attempt=1,
        ),
    )


def _patched_sync_request(
    self: httpx.Client,
    method: str,
    url: Any,
    *args: Any,
    **kwargs: Any,
) -> httpx.Response:
    assert _ORIGINAL_SYNC_REQUEST is not None
    timestamp = datetime.now(UTC)
    started = time.perf_counter()
    request_headers = _normalized_headers(kwargs.get("headers"))
    request_json = _request_json(kwargs)

    status_code = 599
    response_headers: dict[str, str] = {}
    response_json: dict[str, Any] | None = None
    error: str | None = None
    try:
        response = _ORIGINAL_SYNC_REQUEST(self, method, url, *args, **kwargs)
        status_code = response.status_code
        response_headers = dict(response.headers)
        response_json = _response_json(response)
        return response
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        record = _build_record(
            timestamp=timestamp,
            method=method,
            url=str(url),
            request_headers=request_headers,
            request_json=request_json,
            status_code=status_code,
            response_headers=response_headers,
            response_json=response_json,
            error=error,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        _write_record(record)


async def _patched_async_request(
    self: httpx.AsyncClient,
    method: str,
    url: Any,
    *args: Any,
    **kwargs: Any,
) -> httpx.Response:
    assert _ORIGINAL_ASYNC_REQUEST is not None
    timestamp = datetime.now(UTC)
    started = time.perf_counter()
    request_headers = _normalized_headers(kwargs.get("headers"))
    request_json = _request_json(kwargs)

    status_code = 599
    response_headers: dict[str, str] = {}
    response_json: dict[str, Any] | None = None
    error: str | None = None
    try:
        response = await _ORIGINAL_ASYNC_REQUEST(self, method, url, *args, **kwargs)
        status_code = response.status_code
        response_headers = dict(response.headers)
        response_json = _response_json(response)
        return response
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        record = _build_record(
            timestamp=timestamp,
            method=method,
            url=str(url),
            request_headers=request_headers,
            request_json=request_json,
            status_code=status_code,
            response_headers=response_headers,
            response_json=response_json,
            error=error,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        _write_record(record)


def enable_sdk_capture(*, force: bool = False) -> bool:
    """Enable HTTP capture monkeypatching for SDK-level traffic."""
    global _PATCHED, _ORIGINAL_SYNC_REQUEST, _ORIGINAL_ASYNC_REQUEST
    if not force and not _env_truthy("FLIGHTLOG"):
        return False
    with _PATCH_LOCK:
        if _PATCHED:
            return True
        _ORIGINAL_SYNC_REQUEST = httpx.Client.request
        _ORIGINAL_ASYNC_REQUEST = httpx.AsyncClient.request
        httpx.Client.request = _patched_sync_request  # type: ignore[method-assign]
        httpx.AsyncClient.request = _patched_async_request  # type: ignore[method-assign]
        _PATCHED = True
        return True


def disable_sdk_capture() -> None:
    """Disable HTTP capture monkeypatching."""
    global _PATCHED, _ORIGINAL_SYNC_REQUEST, _ORIGINAL_ASYNC_REQUEST
    with _PATCH_LOCK:
        if not _PATCHED:
            return
        if _ORIGINAL_SYNC_REQUEST is not None:
            httpx.Client.request = cast(Any, _ORIGINAL_SYNC_REQUEST)  # type: ignore[method-assign]
        if _ORIGINAL_ASYNC_REQUEST is not None:
            httpx.AsyncClient.request = cast(Any, _ORIGINAL_ASYNC_REQUEST)  # type: ignore[method-assign]
        _ORIGINAL_SYNC_REQUEST = None
        _ORIGINAL_ASYNC_REQUEST = None
        _PATCHED = False
