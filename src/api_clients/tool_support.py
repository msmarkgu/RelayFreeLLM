"""Shared helpers for OpenAI-style tool calling across provider clients.

Only clients that opt in via ``supports_tools`` are routed tool requests.
Responses preserve the OpenAI shape so the Anthropic adapter can translate
them without provider-specific branching.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResponse:
    """Non-streaming provider result containing text and/or tool calls."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def serialize_tools(tools: Any) -> list[dict[str, Any]] | None:
    """Convert internal tool definitions into JSON-serializable dictionaries."""
    if not tools:
        return None
    serialized = []
    for tool in tools:
        if hasattr(tool, "model_dump"):
            serialized.append(tool.model_dump(exclude_none=True))
        elif isinstance(tool, dict):
            serialized.append(tool)
    return serialized or None


def _tool_calls(value: Any) -> list[Any]:
    if not value:
        return []
    return list(value)


def normalize_tool_call(call: Any, index: int = 0) -> dict[str, Any]:
    """Normalize an SDK object or dict into an OpenAI-style tool call."""
    if isinstance(call, dict):
        function = call.get("function") or {}
        return {
            "id": call.get("id") or f"call_{index}",
            "type": "function",
            "function": {
                "name": function.get("name", ""),
                "arguments": function.get("arguments") or "{}",
            },
        }

    function = getattr(call, "function", None)
    return {
        "id": getattr(call, "id", None) or f"call_{index}",
        "type": "function",
        "function": {
            "name": getattr(function, "name", "") or "",
            "arguments": getattr(function, "arguments", None) or "{}",
        },
    }


def tool_calls_from_message(message: Any) -> list[dict[str, Any]]:
    """Extract tool calls from a non-streaming provider message."""
    calls = (
        message.get("tool_calls")
        if isinstance(message, dict)
        else getattr(message, "tool_calls", None)
    )
    return [normalize_tool_call(call, i) for i, call in enumerate(_tool_calls(calls))]


def tool_call_deltas(delta: Any) -> list[dict[str, Any]]:
    """Extract incremental tool-call fragments from a streamed delta."""
    calls = (
        delta.get("tool_calls")
        if isinstance(delta, dict)
        else getattr(delta, "tool_calls", None)
    )
    result: list[dict[str, Any]] = []
    for i, call in enumerate(_tool_calls(calls)):
        if isinstance(call, dict):
            index = call.get("index", i)
            function = call.get("function") or {}
            item: dict[str, Any] = {"index": index}
            if call.get("id"):
                item["id"] = call["id"]
            if call.get("type"):
                item["type"] = call["type"]
            arguments = function.get("arguments")
            name = function.get("name")
            if name or arguments:
                item["function"] = {
                    key: value
                    for key, value in (("name", name), ("arguments", arguments))
                    if value
                }
        else:
            function = getattr(call, "function", None)
            item = {"index": getattr(call, "index", i)}
            if getattr(call, "id", None):
                item["id"] = call.id
            arguments = getattr(function, "arguments", None)
            name = getattr(function, "name", None)
            if name or arguments:
                item["function"] = {
                    key: value
                    for key, value in (("name", name), ("arguments", arguments))
                    if value
                }
        result.append(item)
    return result
