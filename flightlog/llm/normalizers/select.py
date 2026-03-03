"""Normalizer selection by provider family."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from flightlog.llm.models import LLMTurn
from flightlog.llm.normalizers.anthropic import AnthropicNormalizer
from flightlog.llm.normalizers.gemini import GeminiNormalizer
from flightlog.llm.normalizers.openai_compat import OpenAICompatNormalizer


class TurnNormalizer(Protocol):
    def normalize(
        self,
        raw_request: Mapping[str, Any] | None,
        raw_response: Mapping[str, Any] | None,
        meta: Mapping[str, Any],
    ) -> LLMTurn: ...


def select_normalizer(provider_family: str) -> TurnNormalizer:
    normalized = provider_family.strip().lower()
    if normalized == "anthropic":
        return AnthropicNormalizer()
    if normalized == "openai_compat":
        return OpenAICompatNormalizer()
    if normalized == "gemini":
        return GeminiNormalizer()
    raise ValueError(f"Unsupported provider family: {provider_family}")
