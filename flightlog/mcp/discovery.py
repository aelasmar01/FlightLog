"""Discovery helpers for common MCP client configs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _candidate_paths() -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    override = os.environ.get("FLIGHTLOG_CLAUDE_CONFIG")
    if override:
        candidates.append(("claude_desktop", Path(override).expanduser()))

    candidates.extend(
        [
            (
                "claude_desktop",
                Path(
                    "~/Library/Application Support/Claude/claude_desktop_config.json"
                ).expanduser(),
            ),
            ("claude_desktop", Path("~/.config/Claude/claude_desktop_config.json").expanduser()),
            ("claude_desktop", Path("~/.config/claude/claude_desktop_config.json").expanduser()),
        ]
    )
    return candidates


def discover_servers() -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    for client, path in _candidate_paths():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            continue
        for name, config in sorted(servers.items()):
            if not isinstance(config, dict):
                continue
            discovered.append(
                {
                    "client": client,
                    "config_path": str(path),
                    "name": name,
                    "command": config.get("command"),
                    "args": config.get("args", []),
                }
            )
    discovered.sort(key=lambda item: (str(item["client"]), str(item["name"])))
    return discovered
