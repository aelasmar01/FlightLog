"""Normalizer selection by provider family."""

from __future__ import annotations

from flightlog.llm.normalizers.anthropic import AnthropicNormalizer
from flightlog.llm.normalizers.gemini import GeminiNormalizer
from flightlog.llm.normalizers.openai_compat import OpenAICompatNormalizer


def select_normalizer(provider_family: str) -> object:
    normalized = provider_family.strip().lower()
    if normalized == "anthropic":
        return AnthropicNormalizer()
    if normalized == "openai_compat":
        return OpenAICompatNormalizer()
    if normalized == "gemini":
        return GeminiNormalizer()
    raise ValueError(f"Unsupported provider family: {provider_family}")
