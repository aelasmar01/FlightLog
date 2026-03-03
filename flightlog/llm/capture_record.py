"""Raw HTTP capture record schema for LLM request/response ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CaptureRequest(BaseModel):
    method: str
    url: str
    headers: dict[str, str] | None = None
    json_body: dict[str, Any] | None = None


class CaptureResponse(BaseModel):
    status_code: int
    headers: dict[str, str] | None = None
    json_body: dict[str, Any] | None = None
    error: dict[str, Any] | str | None = None


class CaptureTransport(BaseModel):
    latency_ms: float | None = None
    streaming: bool = False
    attempt: int = 1


class CaptureRecord(BaseModel):
    ts: datetime
    session_id: str
    run_id: str
    provider_family: Literal["anthropic", "openai_compat", "gemini"]
    request: CaptureRequest
    response: CaptureResponse
    transport: CaptureTransport = Field(default_factory=CaptureTransport)

    @field_validator("ts", mode="before")
    @classmethod
    def _validate_ts(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("ts must be datetime or RFC3339 string")
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
