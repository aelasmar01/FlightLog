"""Lightweight span capture that writes OTel-style spans to a JSONL file.

No external collector is required. Spans are written to
``<output_root>/otel/spans.jsonl`` and can be post-processed by any tool that
reads JSONL.

Span format (one JSON object per line)::

    {
        "trace_id": "<hex>",
        "span_id": "<hex>",
        "parent_span_id": "<hex|null>",
        "name": "<str>",
        "kind": "CLIENT|SERVER|INTERNAL|...",
        "start_time_iso": "<RFC3339>",
        "end_time_iso": "<RFC3339>",
        "duration_ms": <float>,
        "status": "OK|ERROR|UNSET",
        "attributes": { ... },
        "events": [ { "name": str, "ts": str, "attributes": {...} } ]
    }
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flightlog.json_utils import canonical_json_dumps


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hex_id(n_bytes: int = 8) -> str:
    return os.urandom(n_bytes).hex()


class SpanRecorder:
    """Thread-safe span recorder that appends to a JSONL file."""

    def __init__(self, output_root: Path) -> None:
        self._path = output_root / "otel" / "spans.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def record(self, span: dict[str, Any]) -> None:
        line = canonical_json_dumps(span) + "\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: str = "INTERNAL",
        attributes: dict[str, Any] | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Context manager that records a span on exit.

        The yielded *span_ctx* dict can be used to attach events or set the
        status::

            with recorder.span("mcp.request", attributes={"method": method}) as ctx:
                ctx["status"] = "OK"
                # ... do work ...
        """
        tid = trace_id or _hex_id(16)
        sid = _hex_id(8)
        start_iso = _now_iso()
        start_dt = datetime.now(UTC)

        span_ctx: dict[str, Any] = {
            "trace_id": tid,
            "span_id": sid,
            "parent_span_id": parent_span_id,
            "name": name,
            "kind": kind,
            "start_time_iso": start_iso,
            "status": "UNSET",
            "attributes": dict(attributes or {}),
            "events": [],
        }

        try:
            yield span_ctx
        except Exception:
            span_ctx["status"] = "ERROR"
            raise
        finally:
            end_dt = datetime.now(UTC)
            span_ctx["end_time_iso"] = end_dt.isoformat()
            span_ctx["duration_ms"] = round((end_dt - start_dt).total_seconds() * 1000, 3)
            if span_ctx["status"] == "UNSET":
                span_ctx["status"] = "OK"
            self.record(span_ctx)

    def add_event(
        self,
        span_ctx: dict[str, Any],
        event_name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        span_ctx["events"].append(
            {
                "name": event_name,
                "ts": _now_iso(),
                "attributes": dict(attributes or {}),
            }
        )
