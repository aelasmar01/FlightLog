"""LLM-agnostic turn models and adapters."""

from flightlog.llm.models import LLMTurn, ToolCall, TransportMeta, Usage
from flightlog.llm.serialization import dumps_turn, loads_turn
from flightlog.llm.to_events import to_events

__all__ = [
    "LLMTurn",
    "ToolCall",
    "TransportMeta",
    "Usage",
    "dumps_turn",
    "loads_turn",
    "to_events",
]
