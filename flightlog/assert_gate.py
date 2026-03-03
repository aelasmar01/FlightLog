"""CI regression gate built on pack compare + offline replay checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from flightlog.pack_compare import CompareReport, compare_packs

DEFAULT_POLICY: dict[str, Any] = {
    "no_new_missing_stubs": True,
    "no_new_event_types": False,
    "no_new_tool_types": False,
    "allow_added_event_types": [],
    "max_added_events_by_type": {},
}


@dataclass(frozen=True)
class AssertResult:
    passed: bool
    violations: list[str]
    report: CompareReport
    policy: dict[str, Any]


def load_assert_policy(policy_path: Path | None) -> dict[str, Any]:
    policy = dict(DEFAULT_POLICY)
    if policy_path is None:
        return policy

    raw = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("assert policy must be a mapping")

    for key in DEFAULT_POLICY:
        if key in raw:
            policy[key] = raw[key]
    return policy


def run_assert_gate(
    *, baseline_path: Path, candidate_path: Path, policy_path: Path | None
) -> AssertResult:
    report = compare_packs(baseline_path, candidate_path)
    policy = load_assert_policy(policy_path)
    violations: list[str] = []

    no_new_missing_stubs = bool(policy.get("no_new_missing_stubs", True))
    if no_new_missing_stubs and report.new_missing_stub_mappings:
        violations.append(
            "candidate introduced new missing MCP stub mappings: "
            + str(len(report.new_missing_stub_mappings))
        )

    allow_added = policy.get("allow_added_event_types", [])
    allowed_added = {str(item) for item in allow_added} if isinstance(allow_added, list) else set()

    no_new_event_types = bool(policy.get("no_new_event_types", False))
    if no_new_event_types:
        blocked = [
            event_type for event_type in report.added_event_types if event_type not in allowed_added
        ]
        if blocked:
            violations.append("candidate introduced disallowed event types: " + ", ".join(blocked))

    no_new_tool_types = bool(policy.get("no_new_tool_types", False))
    if no_new_tool_types:
        new_tool_types = [item for item in report.added_event_types if item.startswith("tool.")]
        if new_tool_types:
            violations.append(
                "candidate introduced new tool event types: " + ", ".join(new_tool_types)
            )

    thresholds_raw = policy.get("max_added_events_by_type", {})
    if isinstance(thresholds_raw, dict):
        for event_type, raw_threshold in sorted(thresholds_raw.items()):
            threshold = int(raw_threshold)
            baseline_count = report.baseline.event_counts.get(str(event_type), 0)
            candidate_count = report.candidate.event_counts.get(str(event_type), 0)
            delta = candidate_count - baseline_count
            if delta > threshold:
                violations.append(
                    f"event type '{event_type}' exceeded threshold: "
                    f"delta={delta} threshold={threshold}"
                )

    return AssertResult(
        passed=(len(violations) == 0),
        violations=violations,
        report=report,
        policy=policy,
    )
