"""Core domain models for replay packs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class JsonModel(BaseModel):
    """Base model with deterministic JSON rendering helpers."""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class NormalizedEvent(JsonModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str
    type: str
    session_id: str
    run_id: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ts", mode="before")
    @classmethod
    def validate_ts(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("ts must be datetime or RFC3339 string")
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt


class RedactionReport(JsonModel):
    patterns_matched: dict[str, int] = Field(default_factory=dict)
    replacements: int = 0
    json_keys_masked: dict[str, int] = Field(default_factory=dict)
    excluded_artifacts: list[str] = Field(default_factory=list)

    def bump_pattern(self, name: str, increment: int = 1) -> None:
        self.patterns_matched[name] = self.patterns_matched.get(name, 0) + increment
        self.replacements += increment

    def bump_json_key(self, key: str, increment: int = 1) -> None:
        self.json_keys_masked[key] = self.json_keys_masked.get(key, 0) + increment
        self.replacements += increment


class FlightlogManifest(JsonModel):
    schema_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    timeline_path: str = "timeline.jsonl"
    timeline_sha256: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    redaction_report_path: str = "redaction_report.json"
    extra_sections: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_created_at(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("created_at must be datetime or RFC3339 string")
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
