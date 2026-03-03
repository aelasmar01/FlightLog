"""Common helpers for JSONL ingestors."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            if not isinstance(data, dict):
                continue
            yield line_no, data


def parse_timestamp(raw: dict[str, Any], index: int) -> datetime:
    for key in ("ts", "timestamp", "time", "created_at"):
        value = raw.get(key)
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=UTC)
                return dt
            except ValueError:
                continue
    return datetime.fromtimestamp(index, tz=UTC)


def payload_without_meta(raw: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key not in keys}


def stringify_payload(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
