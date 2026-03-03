"""Offline replay runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from replaypack.mcp.stubgen import load_stub, params_hash
from replaypack.pack_io import open_pack


def _load_stubs(pack_dir: Path) -> dict[str, dict[str, Any]]:
    stubs: dict[str, dict[str, Any]] = {}
    root = pack_dir / "mcp" / "stubs"
    if not root.exists():
        return stubs

    for server_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        merged: dict[str, Any] = {"methods": {}}
        for stub_file in sorted(server_dir.glob("*.json")):
            stub = load_stub(stub_file)
            methods = stub.get("methods", {})
            if not isinstance(methods, dict):
                continue
            for method, mapping in methods.items():
                if not isinstance(mapping, dict):
                    continue
                merged_methods = merged["methods"].setdefault(method, {})
                if isinstance(merged_methods, dict):
                    merged_methods.update(mapping)
        stubs[server_dir.name] = merged
    return stubs


def _has_stub_mapping(stub: dict[str, Any], method: str, params: Any) -> bool:
    methods = stub.get("methods", {})
    if not isinstance(methods, dict):
        return False
    method_map = methods.get(method, {})
    if not isinstance(method_map, dict):
        return False
    return params_hash(params) in method_map


def run_replay(pack_path: Path, *, offline: bool) -> tuple[bool, list[str], int]:
    mismatches: list[str] = []
    event_count = 0

    with open_pack(pack_path) as pack_dir:
        timeline = pack_dir / "timeline.jsonl"
        if not timeline.exists():
            return False, ["timeline.jsonl missing"], 0

        stubs = _load_stubs(pack_dir)
        default_server = sorted(stubs.keys())[0] if stubs else None

        with timeline.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                event_count += 1
                event = json.loads(stripped)
                if event.get("type") != "mcp.request":
                    continue

                payload = event.get("payload", {})
                if not isinstance(payload, dict):
                    mismatches.append("mcp.request payload is not an object")
                    continue
                method = payload.get("method")
                params = payload.get("params", {})
                if not isinstance(method, str):
                    mismatches.append("mcp.request missing method")
                    continue

                server_name = payload.get("server")
                if not isinstance(server_name, str):
                    server_name = default_server

                if offline:
                    if server_name is None:
                        mismatches.append(f"No stub server available for method {method}")
                        continue
                    stub = stubs.get(server_name)
                    if stub is None:
                        mismatches.append(f"Missing stub server '{server_name}'")
                        continue
                    if not _has_stub_mapping(stub, method, params):
                        mismatches.append(
                            f"No stub mapping for server={server_name} method={method}"
                        )

    return len(mismatches) == 0, mismatches, event_count
