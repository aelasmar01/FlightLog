"""Pack diff listing and rendering helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from flightlog.pack_io import open_pack


@dataclass(frozen=True, slots=True)
class DiffEntry:
    event_id: str
    ts: str
    path: str
    artifact: str


def _load_diff_entries(pack_dir: Path) -> list[DiffEntry]:
    timeline_path = pack_dir / "timeline.jsonl"
    if not timeline_path.exists():
        return []

    entries: list[DiffEntry] = []
    with timeline_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            if data.get("type") != "file.diff":
                continue
            payload = data.get("payload", {})
            if not isinstance(payload, dict):
                continue
            path = payload.get("path")
            artifact = payload.get("artifact")
            event_id = data.get("event_id")
            ts = data.get("ts")
            if not all(isinstance(item, str) for item in (path, artifact, event_id, ts)):
                continue
            entries.append(
                DiffEntry(
                    event_id=event_id,
                    ts=ts,
                    path=cast(str, path),
                    artifact=cast(str, artifact),
                )
            )
    return entries


def list_diffs(pack_path: Path) -> list[DiffEntry]:
    with open_pack(pack_path) as pack_dir:
        return _load_diff_entries(pack_dir)


def render_diff(
    pack_path: Path,
    *,
    file_path: str | None,
    event_id: str | None,
    list_only: bool,
) -> tuple[int, str]:
    with open_pack(pack_path) as pack_dir:
        entries = _load_diff_entries(pack_dir)
        if not entries:
            return 1, "No diff events found."

        selected = entries
        if file_path is not None:
            selected = [entry for entry in selected if entry.path == file_path]
        if event_id is not None:
            selected = [entry for entry in selected if entry.event_id == event_id]
        if not selected:
            return 1, "Requested diff was not found."

        if list_only:
            lines = [f"{entry.path}\t{entry.ts}\t{entry.event_id}" for entry in selected]
            return 0, "\n".join(lines)

        rendered: list[str] = []
        for entry in selected:
            artifact_path = pack_dir / entry.artifact
            if not artifact_path.exists():
                return 1, f"Missing diff artifact: {entry.artifact}"
            content = artifact_path.read_text(encoding="utf-8", errors="replace")
            rendered.append(f"# {entry.path} [{entry.event_id}]\n{content}".rstrip())
        return 0, "\n\n".join(rendered)
