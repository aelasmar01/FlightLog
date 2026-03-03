"""Cross-pack regression comparisons."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flightlog.json_utils import canonical_json_dumps
from flightlog.pack_io import open_pack
from flightlog.replay_runner import run_replay


@dataclass(frozen=True)
class PackSummary:
    total_events: int
    event_counts: dict[str, int]
    mcp_methods: list[str]
    model_response_hashes: list[str]
    missing_stub_mappings: list[str]


@dataclass(frozen=True)
class CompareReport:
    baseline: PackSummary
    candidate: PackSummary
    added_event_types: list[str]
    removed_event_types: list[str]
    new_mcp_methods: list[str]
    missing_mcp_methods: list[str]
    new_missing_stub_mappings: list[str]
    model_response_hashes_changed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": {
                "total_events": self.baseline.total_events,
                "event_counts": self.baseline.event_counts,
                "mcp_methods": self.baseline.mcp_methods,
                "model_response_hashes": self.baseline.model_response_hashes,
                "missing_stub_mappings": self.baseline.missing_stub_mappings,
            },
            "candidate": {
                "total_events": self.candidate.total_events,
                "event_counts": self.candidate.event_counts,
                "mcp_methods": self.candidate.mcp_methods,
                "model_response_hashes": self.candidate.model_response_hashes,
                "missing_stub_mappings": self.candidate.missing_stub_mappings,
            },
            "added_event_types": self.added_event_types,
            "removed_event_types": self.removed_event_types,
            "new_mcp_methods": self.new_mcp_methods,
            "missing_mcp_methods": self.missing_mcp_methods,
            "new_missing_stub_mappings": self.new_missing_stub_mappings,
            "model_response_hashes_changed": self.model_response_hashes_changed,
        }


def _iter_timeline(pack_path: Path) -> list[dict[str, Any]]:
    with open_pack(pack_path) as pack_dir:
        timeline = pack_dir / "timeline.jsonl"
        events: list[dict[str, Any]] = []
        with timeline.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                data = json.loads(stripped)
                if isinstance(data, dict):
                    events.append(data)
        return events


def summarize_pack(pack_path: Path) -> PackSummary:
    events = _iter_timeline(pack_path)
    counts: Counter[str] = Counter()
    mcp_methods: set[str] = set()
    model_response_hashes: list[str] = []

    for event in events:
        event_type_value = event.get("type")
        event_type = event_type_value if isinstance(event_type_value, str) else "unknown"
        counts[event_type] += 1

        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        if event_type == "mcp.request":
            method = payload.get("method")
            if isinstance(method, str):
                mcp_methods.add(method)

        if event_type == "model.response":
            model_response_hashes.append(canonical_json_dumps(payload))

    ok, mismatches, _ = run_replay(pack_path, offline=True)
    missing_stub_mappings: set[str] = set()
    if not ok:
        for mismatch in mismatches:
            if mismatch.startswith("No stub mapping"):
                missing_stub_mappings.add(mismatch)

    return PackSummary(
        total_events=len(events),
        event_counts={key: counts[key] for key in sorted(counts)},
        mcp_methods=sorted(mcp_methods),
        model_response_hashes=sorted(model_response_hashes),
        missing_stub_mappings=sorted(missing_stub_mappings),
    )


def compare_packs(baseline_path: Path, candidate_path: Path) -> CompareReport:
    baseline = summarize_pack(baseline_path)
    candidate = summarize_pack(candidate_path)

    baseline_event_types = set(baseline.event_counts.keys())
    candidate_event_types = set(candidate.event_counts.keys())

    baseline_methods = set(baseline.mcp_methods)
    candidate_methods = set(candidate.mcp_methods)

    baseline_missing = set(baseline.missing_stub_mappings)
    candidate_missing = set(candidate.missing_stub_mappings)

    return CompareReport(
        baseline=baseline,
        candidate=candidate,
        added_event_types=sorted(candidate_event_types - baseline_event_types),
        removed_event_types=sorted(baseline_event_types - candidate_event_types),
        new_mcp_methods=sorted(candidate_methods - baseline_methods),
        missing_mcp_methods=sorted(baseline_methods - candidate_methods),
        new_missing_stub_mappings=sorted(candidate_missing - baseline_missing),
        model_response_hashes_changed=(
            baseline.model_response_hashes != candidate.model_response_hashes
        ),
    )


def render_compare_text(report: CompareReport) -> str:
    lines = [
        "Flightlog Pack Compare",
        f"baseline.total_events={report.baseline.total_events}",
        f"candidate.total_events={report.candidate.total_events}",
        "event_counts.baseline=" + canonical_json_dumps(report.baseline.event_counts),
        "event_counts.candidate=" + canonical_json_dumps(report.candidate.event_counts),
        "added_event_types=" + ",".join(report.added_event_types),
        "removed_event_types=" + ",".join(report.removed_event_types),
        "new_mcp_methods=" + ",".join(report.new_mcp_methods),
        "missing_mcp_methods=" + ",".join(report.missing_mcp_methods),
        "new_missing_stub_mappings=" + str(len(report.new_missing_stub_mappings)),
        "model_response_hashes_changed="
        + ("true" if report.model_response_hashes_changed else "false"),
    ]
    return "\n".join(lines)
