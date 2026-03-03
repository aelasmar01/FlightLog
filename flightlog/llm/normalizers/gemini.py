"""Gemini payload normalization placeholder.

Issue 04 fills out Gemini functionCall/candidates normalization.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flightlog.llm.models import LLMTurn


class GeminiNormalizer:
    """Placeholder normalizer for Gemini payloads."""

    def normalize(
        self,
        raw_request: Mapping[str, Any] | None,
        raw_response: Mapping[str, Any] | None,
        meta: Mapping[str, Any],
    ) -> LLMTurn:
        raise NotImplementedError("Gemini normalization is implemented in Issue 04.")
