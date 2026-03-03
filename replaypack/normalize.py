"""Timeline normalization, artifact extraction, and diff generation."""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from replaypack.models import NormalizedEvent

ARTIFACT_THRESHOLD_BYTES = 4096


def _stable_uuid(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "|".join(parts)))


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _extract_large_payloads(
    value: Any,
    *,
    event_id: str,
    counter: list[int],
    artifacts: dict[str, bytes],
    threshold_bytes: int,
) -> Any:
    if isinstance(value, str):
        payload = value.encode("utf-8")
        if len(payload) > threshold_bytes:
            counter[0] += 1
            artifact_key = f"payloads/{event_id}_{counter[0]}.txt"
            artifacts[artifact_key] = payload
            return {
                "artifact_ref": f"artifacts/{artifact_key}",
                "size_bytes": len(payload),
            }
        return value
    if isinstance(value, bytes):
        if len(value) > threshold_bytes:
            counter[0] += 1
            artifact_key = f"payloads/{event_id}_{counter[0]}.bin"
            artifacts[artifact_key] = value
            return {
                "artifact_ref": f"artifacts/{artifact_key}",
                "size_bytes": len(value),
            }
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {
            key: _extract_large_payloads(
                item,
                event_id=event_id,
                counter=counter,
                artifacts=artifacts,
                threshold_bytes=threshold_bytes,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _extract_large_payloads(
                item,
                event_id=event_id,
                counter=counter,
                artifacts=artifacts,
                threshold_bytes=threshold_bytes,
            )
            for item in value
        ]
    return value


def _build_patch(before_text: str, after_text: str, path: str) -> str:
    before_lines = before_text.splitlines(keepends=True)
    after_lines = after_text.splitlines(keepends=True)
    patch = "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=path,
            tofile=path,
            lineterm="",
        )
    )
    if patch and not patch.endswith("\n"):
        patch += "\n"
    return patch


def _extract_log_diff(payload: dict[str, Any]) -> tuple[str, str] | None:
    path_value = payload.get("path") or payload.get("file") or payload.get("file_path")
    path = _normalize_path(str(path_value)) if path_value else ""

    for key in ("patch", "diff", "unified_diff"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            patch = value
            if not patch.endswith("\n"):
                patch += "\n"
            if "---" in patch and "+++" in patch and "@@" in patch:
                if not path:
                    path = "unknown.txt"
                return path, patch

    before = payload.get("before") or payload.get("old_content")
    after = payload.get("after") or payload.get("new_content")
    if isinstance(before, str) and isinstance(after, str) and path:
        patch = _build_patch(before, after, path)
        if patch.strip():
            return path, patch
    return None


def _collect_files(root: Path) -> set[str]:
    return {
        str(path.relative_to(root)).replace("\\", "/") for path in root.rglob("*") if path.is_file()
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _snapshot_diffs(
    workspace_before: Path,
    workspace_after: Path,
    existing_paths: set[str],
    session_id: str,
    run_id: str,
    start_ts: datetime,
) -> tuple[list[NormalizedEvent], dict[str, bytes]]:
    diff_events: list[NormalizedEvent] = []
    diff_artifacts: dict[str, bytes] = {}

    before_files = _collect_files(workspace_before)
    after_files = _collect_files(workspace_after)
    changed_paths = sorted(before_files | after_files)

    ts_counter = 0
    for rel_path in changed_paths:
        normalized_path = _normalize_path(rel_path)
        if normalized_path in existing_paths:
            continue

        before_text = ""
        after_text = ""
        before_path = workspace_before / rel_path
        after_path = workspace_after / rel_path
        if before_path.exists():
            before_text = _read_text(before_path)
        if after_path.exists():
            after_text = _read_text(after_path)
        if before_text == after_text:
            continue

        patch = _build_patch(before_text, after_text, normalized_path)
        if not patch.strip():
            continue

        ts_counter += 1
        event_id = _stable_uuid(session_id, run_id, normalized_path, "snapshot")
        artifact_key = f"diffs/{normalized_path}.{event_id}.patch"
        diff_artifacts[artifact_key] = patch.encode("utf-8")
        diff_events.append(
            NormalizedEvent(
                event_id=event_id,
                ts=start_ts + timedelta(seconds=ts_counter),
                source="snapshot_diff",
                type="file.diff",
                session_id=session_id,
                run_id=run_id,
                payload={
                    "path": normalized_path,
                    "artifact": f"artifacts/{artifact_key}",
                    "origin": "snapshot",
                },
            )
        )

    return diff_events, diff_artifacts


def normalize_events(
    events: Iterable[NormalizedEvent],
    *,
    artifact_threshold_bytes: int = ARTIFACT_THRESHOLD_BYTES,
    workspace_before: Path | None = None,
    workspace_after: Path | None = None,
) -> tuple[list[NormalizedEvent], dict[str, bytes]]:
    normalized: list[NormalizedEvent] = []
    artifacts: dict[str, bytes] = {}
    diff_events: list[NormalizedEvent] = []
    log_diff_paths: set[str] = set()

    for event in events:
        counter = [0]
        payload = _extract_large_payloads(
            event.payload,
            event_id=event.event_id,
            counter=counter,
            artifacts=artifacts,
            threshold_bytes=artifact_threshold_bytes,
        )
        normalized_event = event.model_copy(update={"payload": payload}, deep=True)
        normalized.append(normalized_event)

        if not isinstance(payload, dict):
            continue
        log_diff = _extract_log_diff(payload)
        if log_diff is None:
            continue

        path, patch = log_diff
        path = _normalize_path(path)
        log_diff_paths.add(path)
        event_id = _stable_uuid(event.event_id, path, "log")
        artifact_key = f"diffs/{path}.{event_id}.patch"
        artifacts[artifact_key] = patch.encode("utf-8")
        diff_events.append(
            NormalizedEvent(
                event_id=event_id,
                ts=event.ts,
                source=event.source,
                type="file.diff",
                session_id=event.session_id,
                run_id=event.run_id,
                payload={
                    "path": path,
                    "artifact": f"artifacts/{artifact_key}",
                    "origin": "log",
                },
            )
        )

    if normalized:
        last_event = normalized[-1]
        base_session = last_event.session_id
        base_run = last_event.run_id
        base_ts = last_event.ts
    else:
        base_session = "session"
        base_run = "run"
        base_ts = datetime.now(UTC)

    if workspace_before is not None and workspace_after is not None:
        snapshot_events, snapshot_artifacts = _snapshot_diffs(
            workspace_before=workspace_before,
            workspace_after=workspace_after,
            existing_paths=log_diff_paths,
            session_id=base_session,
            run_id=base_run,
            start_ts=base_ts,
        )
        diff_events.extend(snapshot_events)
        artifacts.update(snapshot_artifacts)

    normalized.extend(diff_events)
    normalized.sort(key=lambda event: (event.ts, event.event_id))
    return normalized, artifacts
