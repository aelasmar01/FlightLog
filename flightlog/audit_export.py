"""Audit/governance export for packs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from flightlog.json_utils import canonical_json_dumps
from flightlog.pack_io import open_pack


def _load_governance(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {}
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("audit config must be a mapping")
    return {str(key): value for key, value in sorted(raw.items())}


def build_audit_report(pack_path: Path, *, config_path: Path | None = None) -> dict[str, Any]:
    governance = _load_governance(config_path)

    with open_pack(pack_path) as pack_dir:
        manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
        redaction_report = json.loads(
            (pack_dir / "redaction_report.json").read_text(encoding="utf-8")
        )

        timeline_path = pack_dir / "timeline.jsonl"
        event_counts: dict[str, int] = {}
        tool_names: set[str] = set()
        mcp_methods: set[str] = set()
        total_events = 0

        with timeline_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                event = json.loads(stripped)
                if not isinstance(event, dict):
                    continue
                total_events += 1

                event_type_raw = event.get("type")
                event_type = event_type_raw if isinstance(event_type_raw, str) else "unknown"
                event_counts[event_type] = event_counts.get(event_type, 0) + 1

                payload = event.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}

                if event_type == "tool.call":
                    for key in ("tool", "name", "tool_name"):
                        value = payload.get(key)
                        if isinstance(value, str):
                            tool_names.add(value)
                            break
                if event_type == "mcp.request":
                    method = payload.get("method")
                    if isinstance(method, str):
                        mcp_methods.add(method)

    artifacts_raw = manifest.get("artifacts", {})
    artifacts = artifacts_raw if isinstance(artifacts_raw, dict) else {}

    report = {
        "pack": {
            "schema_version": manifest.get("schema_version"),
            "timeline_sha256": manifest.get("timeline_sha256"),
            "artifact_hashes": {k: artifacts[k] for k in sorted(artifacts)},
            "artifact_count": len(artifacts),
        },
        "redaction": redaction_report,
        "events": {
            "total": total_events,
            "counts_by_type": {k: event_counts[k] for k in sorted(event_counts)},
            "tool_names": sorted(tool_names),
            "mcp_methods": sorted(mcp_methods),
        },
        "governance": governance,
    }
    return report


def write_audit_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json_dumps(report) + "\n", encoding="utf-8")


def write_audit_csv(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    events = report.get("events", {})
    counts = events.get("counts_by_type", {}) if isinstance(events, dict) else {}
    methods = events.get("mcp_methods", []) if isinstance(events, dict) else []
    tools = events.get("tool_names", []) if isinstance(events, dict) else []

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "name", "value"])
        for event_type in sorted(counts):
            writer.writerow(["counts_by_type", event_type, counts[event_type]])
        for method in methods if isinstance(methods, list) else []:
            writer.writerow(["mcp_methods", method, "1"])
        for tool in tools if isinstance(tools, list) else []:
            writer.writerow(["tool_names", tool, "1"])


def export_audit(
    *,
    pack_path: Path,
    out_json: Path,
    out_csv: Path | None,
    config_path: Path | None,
) -> dict[str, Any]:
    report = build_audit_report(pack_path, config_path=config_path)
    write_audit_json(out_json, report)
    if out_csv is not None:
        write_audit_csv(out_csv, report)
    return report
