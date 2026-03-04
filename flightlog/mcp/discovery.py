"""Discovery helpers for common MCP client configs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _parse_mcp_servers_block(
    client: str, config_path: Path, data: dict[str, Any]
) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        return discovered
    for name, config in sorted(servers.items()):
        if not isinstance(config, dict):
            continue
        discovered.append(
            {
                "client": client,
                "config_path": str(config_path),
                "name": name,
                "command": config.get("command"),
                "args": config.get("args", []),
            }
        )
    return discovered


# ---------------------------------------------------------------------------
# Backend: Claude Desktop
# ---------------------------------------------------------------------------


def _claude_desktop_paths() -> list[Path]:
    override = os.environ.get("FLIGHTLOG_CLAUDE_CONFIG")
    if override:
        return [Path(override).expanduser()]
    return [
        Path("~/Library/Application Support/Claude/claude_desktop_config.json").expanduser(),
        Path("~/.config/Claude/claude_desktop_config.json").expanduser(),
        Path("~/.config/claude/claude_desktop_config.json").expanduser(),
    ]


def _discover_claude_desktop() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in _claude_desktop_paths():
        data = _load_json(path)
        if data is not None:
            results.extend(_parse_mcp_servers_block("claude_desktop", path, data))
    return results


# ---------------------------------------------------------------------------
# Backend: Cursor
# ---------------------------------------------------------------------------


def _cursor_paths() -> list[Path]:
    return [
        Path("~/.cursor/mcp.json").expanduser(),
        Path(
            "~/.config/Cursor/User/globalStorage/cursor.cursor-ai-ide/mcp_config.json"
        ).expanduser(),
    ]


def _discover_cursor() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in _cursor_paths():
        data = _load_json(path)
        if data is not None:
            results.extend(_parse_mcp_servers_block("cursor", path, data))
    return results


# ---------------------------------------------------------------------------
# Backend: Zed
# ---------------------------------------------------------------------------


def _zed_paths() -> list[Path]:
    return [
        Path("~/.config/zed/settings.json").expanduser(),
        Path("~/Library/Application Support/Zed/settings.json").expanduser(),
    ]


def _discover_zed() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in _zed_paths():
        data = _load_json(path)
        if data is not None:
            results.extend(_parse_mcp_servers_block("zed", path, data))
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_BACKEND_MAP: dict[str, Any] = {
    "claude_desktop": _discover_claude_desktop,
    "cursor": _discover_cursor,
    "zed": _discover_zed,
}


def discover_servers(
    *,
    client: str = "auto",
    config_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Discover MCP servers from client configs.

    Args:
        client: Backend(s) to query. ``"auto"`` queries all backends.
                Values: ``"auto"``, ``"claude_desktop"``, ``"cursor"``, ``"zed"``.
        config_path: Parse this file directly (overrides *client*).

    Returns:
        List of server dicts sorted by (client, name).
    """
    if config_path is not None:
        data = _load_json(config_path)
        discovered = _parse_mcp_servers_block("custom", config_path, data or {})
    elif client == "auto":
        seen: set[tuple[str, Any]] = set()
        discovered = []
        for fn in _BACKEND_MAP.values():
            for item in fn():
                key = (item["name"], item.get("command"))
                if key not in seen:
                    seen.add(key)
                    discovered.append(item)
    elif client in _BACKEND_MAP:
        discovered = _BACKEND_MAP[client]()
    else:
        raise ValueError(
            f"Unknown client: {client!r}. Choose from: auto, {', '.join(_BACKEND_MAP)}"
        )

    discovered.sort(key=lambda item: (str(item["client"]), str(item["name"])))
    return discovered
