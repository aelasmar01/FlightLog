"""Privacy-first redaction for artifact payloads."""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from replaypack.json_utils import canonical_json_dumps
from replaypack.models import RedactionReport

REDACTED_TOKEN = "***REDACTED***"


DEFAULT_REDACTION_CONFIG: dict[str, Any] = {
    "regex_rules": [
        {
            "name": "authorization_bearer",
            "pattern": r"(?i)(authorization\\s*[:=]\\s*bearer\\s+)([a-z0-9._\\-]+)",
            "mask_groups": [2],
            "replacement": REDACTED_TOKEN,
        },
        {
            "name": "openai_api_key",
            "pattern": r"sk-[a-zA-Z0-9]{20,}",
            "replacement": REDACTED_TOKEN,
        },
        {
            "name": "email",
            "pattern": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}",
            "replacement": REDACTED_TOKEN,
        },
    ],
    "json_keys": ["api_key", "authorization", "token", "secret", "password"],
    "exclude_paths": [],
}


@dataclass(slots=True)
class RegexRule:
    name: str
    pattern: str
    replacement: str = REDACTED_TOKEN
    mask_groups: tuple[int, ...] = ()

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.pattern)


def load_redaction_config(config_path: Path | None) -> dict[str, Any]:
    config = {
        "regex_rules": list(DEFAULT_REDACTION_CONFIG["regex_rules"]),
        "json_keys": list(DEFAULT_REDACTION_CONFIG["json_keys"]),
        "exclude_paths": list(DEFAULT_REDACTION_CONFIG["exclude_paths"]),
    }
    if config_path is None:
        return config

    user_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(user_data, dict):
        raise ValueError("redaction config must be a mapping")

    for key in ("regex_rules", "json_keys", "exclude_paths"):
        if key in user_data:
            value = user_data[key]
            if not isinstance(value, list):
                raise ValueError(f"redaction config '{key}' must be a list")
            config[key] = value
    return config


def _build_rules(config: Mapping[str, Any]) -> list[RegexRule]:
    rules: list[RegexRule] = []
    for raw in config.get("regex_rules", []):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "unnamed_rule"))
        pattern = str(raw.get("pattern", ""))
        if not pattern:
            continue
        replacement = str(raw.get("replacement", REDACTED_TOKEN))
        mask_groups_raw = raw.get("mask_groups", [])
        mask_groups: tuple[int, ...]
        if isinstance(mask_groups_raw, list):
            mask_groups = tuple(int(item) for item in mask_groups_raw)
        else:
            mask_groups = ()
        rules.append(
            RegexRule(
                name=name,
                pattern=pattern,
                replacement=replacement,
                mask_groups=mask_groups,
            )
        )
    return rules


def _apply_group_mask(match: re.Match[str], replacement: str, groups: tuple[int, ...]) -> str:
    if not groups:
        return replacement

    full = match.group(0)
    match_start = match.start(0)
    spans: list[tuple[int, int]] = []
    for group_idx in groups:
        try:
            start, end = match.span(group_idx)
        except IndexError:
            continue
        if start < 0 or end < 0:
            continue
        spans.append((start - match_start, end - match_start))
    if not spans:
        return replacement

    spans.sort()
    chunks: list[str] = []
    cursor = 0
    for start, end in spans:
        if start < cursor:
            continue
        chunks.append(full[cursor:start])
        chunks.append(replacement)
        cursor = end
    chunks.append(full[cursor:])
    return "".join(chunks)


def redact_text(text: str, config: Mapping[str, Any], report: RedactionReport) -> str:
    output = text
    for rule in _build_rules(config):
        pattern = rule.compile()
        replacement_text = rule.replacement
        mask_groups = rule.mask_groups

        def replace(
            match: re.Match[str],
            _replacement: str = replacement_text,
            _groups: tuple[int, ...] = mask_groups,
        ) -> str:
            return _apply_group_mask(match, _replacement, _groups)

        output, count = pattern.subn(replace, output)
        if count:
            report.bump_pattern(rule.name, count)
    return output


def _redact_json_keys(value: Any, sensitive_keys: set[str], report: RedactionReport) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in sensitive_keys:
                report.bump_json_key(lowered)
                redacted[key] = REDACTED_TOKEN
            else:
                redacted[key] = _redact_json_keys(item, sensitive_keys, report)
        return redacted
    if isinstance(value, list):
        return [_redact_json_keys(item, sensitive_keys, report) for item in value]
    return value


def redact_artifacts(
    artifacts: Mapping[str, bytes | str],
    config: Mapping[str, Any],
) -> tuple[dict[str, bytes], RedactionReport]:
    report = RedactionReport()
    excluded_patterns = [str(item) for item in config.get("exclude_paths", [])]
    sensitive_keys = {str(item).lower() for item in config.get("json_keys", [])}

    redacted_artifacts: dict[str, bytes] = {}
    for path, raw_value in sorted(artifacts.items()):
        normalized_path = path.replace("\\", "/")
        if any(fnmatch.fnmatch(normalized_path, pattern) for pattern in excluded_patterns):
            report.excluded_artifacts.append(normalized_path)
            continue

        if isinstance(raw_value, bytes):
            text = raw_value.decode("utf-8", errors="replace")
        else:
            text = raw_value
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                decoded = json.loads(text)
                decoded = _redact_json_keys(decoded, sensitive_keys, report)
                text = canonical_json_dumps(decoded)
            except json.JSONDecodeError:
                pass

        text = redact_text(text, config, report)
        redacted_artifacts[normalized_path] = text.encode("utf-8")

    return redacted_artifacts, report
