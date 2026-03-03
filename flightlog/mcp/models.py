"""MCP transcript domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class McpMessage(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    direction: Literal["client->server", "server->client"]
    kind: Literal["request", "response", "notification"]
    method: str | None = None
    request_id: str | int | None = None
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


class McpTranscript(BaseModel):
    server_name: str
    session_id: str
    messages: list[McpMessage] = Field(default_factory=list)

    def append(self, message: McpMessage) -> None:
        self.messages.append(message)
