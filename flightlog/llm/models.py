"""Canonical LLM-agnostic turn models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Usage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class TransportMeta(BaseModel):
    url: str | None = None
    status_code: int | None = None
    latency_ms: float | None = None
    streaming: bool = False
    attempt: int = 1
    request_id: str | None = None


class ToolCall(BaseModel):
    id: str | None = None
    name: str
    arguments_json: dict[str, Any] = Field(default_factory=dict)
    index: int | None = None


class LLMTurn(BaseModel):
    provider: str
    model: str | None = None
    session_id: str
    timestamp: datetime
    input_messages: list[dict[str, Any]] = Field(default_factory=list)
    output_message: dict[str, Any] | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage | None = None
    cost_usd: float | None = None
    raw_request: dict[str, Any] | None = None
    raw_response: dict[str, Any] | None = None
    transport: TransportMeta | None = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def _validate_timestamp(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            timestamp = value
        elif isinstance(value, str):
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("timestamp must be datetime or RFC3339 string")
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=UTC)
        return timestamp
