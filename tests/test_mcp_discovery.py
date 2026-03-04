import json
from pathlib import Path

import pytest

from flightlog.mcp.discovery import discover_servers


def test_mcp_discovery_from_env_override(tmp_path: Path, monkeypatch) -> None:
    config = {
        "mcpServers": {
            "demo": {
                "command": "python",
                "args": ["-m", "demo.server"],
            }
        }
    }
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    monkeypatch.setenv("FLIGHTLOG_CLAUDE_CONFIG", str(config_path))

    discovered = discover_servers()
    assert len(discovered) == 1
    assert discovered[0]["name"] == "demo"
    assert discovered[0]["command"] == "python"


def test_discover_servers_config_path_override(tmp_path: Path) -> None:
    config = {
        "mcpServers": {
            "myserver": {"command": "node", "args": ["server.js"]},
        }
    }
    config_path = tmp_path / "custom_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    discovered = discover_servers(config_path=config_path)
    assert len(discovered) == 1
    assert discovered[0]["name"] == "myserver"
    assert discovered[0]["client"] == "custom"
    assert discovered[0]["command"] == "node"


def test_discover_servers_specific_client_empty(tmp_path: Path, monkeypatch) -> None:
    # Cursor backend should return empty when no config file exists
    monkeypatch.setattr(
        "flightlog.mcp.discovery._cursor_paths",
        lambda: [tmp_path / "nonexistent.json"],
    )
    result = discover_servers(client="cursor")
    assert result == []


def test_discover_servers_unknown_client_raises() -> None:
    with pytest.raises(ValueError, match="Unknown client"):
        discover_servers(client="bogus")


def test_discover_servers_zed_backend(tmp_path: Path, monkeypatch) -> None:
    config = {"mcpServers": {"zed-tool": {"command": "zed-server", "args": []}}}
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    monkeypatch.setattr(
        "flightlog.mcp.discovery._zed_paths",
        lambda: [config_path],
    )
    discovered = discover_servers(client="zed")
    assert len(discovered) == 1
    assert discovered[0]["client"] == "zed"
    assert discovered[0]["name"] == "zed-tool"


def test_discover_servers_auto_deduplicates(tmp_path: Path, monkeypatch) -> None:
    config = {"mcpServers": {"shared": {"command": "server", "args": []}}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    # Make both claude and cursor point to same config
    monkeypatch.setattr(
        "flightlog.mcp.discovery._claude_desktop_paths",
        lambda: [config_path],
    )
    monkeypatch.setattr(
        "flightlog.mcp.discovery._cursor_paths",
        lambda: [config_path],
    )
    monkeypatch.setattr("flightlog.mcp.discovery._zed_paths", lambda: [])

    discovered = discover_servers(client="auto")
    # Should de-duplicate by (name, command)
    assert len(discovered) == 1
    assert discovered[0]["name"] == "shared"
