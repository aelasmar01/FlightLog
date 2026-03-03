import json
from pathlib import Path

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
