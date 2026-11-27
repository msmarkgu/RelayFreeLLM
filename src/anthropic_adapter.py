"""Anthropic Messages ⇄ internal Chat Completions translation.

This module is protocol-only: it converts Anthropic requests into the
gateway's internal ``ChatCompletionRequest`` and translates internal
responses/streams back into Anthropic messages and SSE events.
"""

import json
import uuid
from typing import Any, Literal, Union

from pydantic import BaseModel

from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ToolCall,
)


# ── Anthropic request models ────────────────────────────────────────


class AnthropicTextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class AnthropicImageSource(BaseModel):
    type: str
    media_type: str | None = None
    data: str | None = None
    url: str | None = None


class AnthropicImageBlock(BaseModel):
    type: Literal["image"] = "image"
    source: AnthropicImageSource


class AnthropicToolUseBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any] = {}


class AnthropicToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[Any] | None = None
    is_error: bool = False


class AnthropicThinkingBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: str | None = None


ContentBlock = Union[
    AnthropicTextBlock,
    AnthropicImageBlock,
    AnthropicToolUseBlock,
    AnthropicToolResultBlock,
    AnthropicThinkingBlock,
]


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]


class AnthropicTool(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = {}


class AnthropicToolChoice(BaseModel):
    type: str
    name: str | None = None


class AnthropicThinking(BaseModel):
    type: str = "enabled"
    budget_tokens: int | None = None


class MessagesRequest(BaseModel):
    model: str = "claude-sonnet-5-5"
    max_tokens: int = 4096
    messages: list[AnthropicMessage]
    system: str | list[AnthropicTextBlock] | None = None
    tools: list[AnthropicTool] | None = None
    tool_choice: AnthropicToolChoice | None = None
    thinking: AnthropicThinking | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False


# ── Helpers ─────────────────────────────────────────────────────────


def _new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:24]}"


def _new_tool_id() -> str:
    return f"toolu_{uuid.uuid4().hex[:24]}"


def _estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3) if text else 0


def _block_text(content: str | list[Any] | None) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "tool_result":
                parts.append(_block_text(block.get("content")))
        elif isinstance(block, AnthropicTextBlock):
            parts.append(block.text)
    return "\n".join(part for part in parts if part)


def _image_part(block: AnthropicImageBlock) -> dict[str, Any]:
    source = block.source
    if source.type == "base64" and source.data:
        media_type = source.media_type or "image/png"
        url = f"data:{media_type};base64,{source.data}"
    else:
        url = source.url or ""
    return {"type": "image_url", "image_url": {"url": url}}


def _tool_choice(choice: AnthropicToolChoice | None) -> str | dict | None:
    if choice is None:
        return None
    if choice.type == "any":
        return "required"
    if choice.type == "tool" and choice.name:
        return {"type": "function", "function": {"name": choice.name}}
    return "auto"


# ── Anthropic → internal ────────────────────────────────────────────


def to_chat_request(request: MessagesRequest) -> ChatCompletionRequest:
    """Translate an Anthropic Messages request into the internal schema."""
    messages: list[ChatMessage] = []

    if request.system:
        system_text = (
            request.system
            if isinstance(request.system, str)
            else _block_text([b.model_dump() for b in request.system])
        )
        messages.append(ChatMessage(role="system", content=system_text))

    for message in request.messages:
        if isinstance(message.content, str):
            messages.append(ChatMessage(role=message.role, content=message.content))
            continue

        pending_parts: list[Any] = []
        pending_tool_calls: list[dict[str, Any]] = []

        def flush() -> None:
            if pending_tool_calls or pending_parts:
                messages.append(
                    ChatMessage(
                        role=message.role,
                        content=pending_parts or (None if pending_tool_calls else ""),
                        tool_calls=pending_tool_calls or None,
                    )
                )
                pending_parts.clear()
                pending_tool_calls.clear()

        for block in message.content:
            if isinstance(block, AnthropicToolResultBlock):
                flush()
                messages.append(
                    ChatMessage(
                        role="tool",
                        content=_block_text(block.content),
                        tool_call_id=block.tool_use_id,
                    )
                )
            elif isinstance(block, AnthropicToolUseBlock):
                pending_tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input),
                        },
                    }
                )
            elif isinstance(block, AnthropicImageBlock):
                pending_parts.append(_image_part(block))
            elif isinstance(block, (AnthropicTextBlock, AnthropicThinkingBlock)):
                text = (
                    block.text
                    if isinstance(block, AnthropicTextBlock)
                    else block.thinking
                )
                if text:
                    pending_parts.append({"type": "text", "text": text})
        flush()

    tools = None
    if request.tools:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in request.tools
        ]

    return ChatCompletionRequest(
        model=request.model,
        messages=messages,
        max_tokens=request.max_tokens,
        temperature=request.temperature if request.temperature is not None else 0.8,
        stream=request.stream,
        tools=tools,
        tool_choice=_tool_choice(request.tool_choice),
    )


# ── Internal → Anthropic (non-streaming) ────────────────────────────


def _tool_use_block(call: ToolCall) -> dict[str, Any]:
    try:
        arguments = json.loads(call.function.arguments)
    except (ValueError, TypeError):
        arguments = {}
    return {
        "type": "tool_use",
        "id": call.id,
        "name": call.function.name,
        "input": arguments,
    }


def from_chat_response(
    response: ChatCompletionResponse, requested_model: str
) -> dict[str, Any]:
    """Translate an internal completion into an Anthropic message object."""
    choice = response.choices[0]
    tool_calls = choice.message.tool_calls or []
    content: list[dict[str, Any]] = []
    if choice.message.content:
        content.append({"type": "text", "text": choice.message.content})
    content.extend(_tool_use_block(call) for call in tool_calls)

    return {
        "id": _new_message_id(),
        "type": "message",
        "role": "assistant",
        "model": requested_model,
        "content": content,
        "stop_reason": "tool_use" if tool_calls else "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        },
    }


def count_request_tokens(request: MessagesRequest) -> int:
    """Estimate input tokens for an Anthropic Messages request."""
    system_tokens = (
        _estimate_tokens(_block_text(request.system)) if request.system else 0
    )
    return system_tokens + sum(
        _estimate_tokens(_block_text(message.content))
        for message in request.messages
    )


def error_payload(message: str, error_type: str = "api_error") -> dict[str, Any]:
    """Anthropic-style error envelope."""
    return {"type": "error", "error": {"type": error_type, "message": message}}


# ── Internal → Anthropic (streaming) ───────────────────────────────


async def stream_anthropic_events(
    inner, request: MessagesRequest
) -> Any:
    """Yield Anthropic SSE event dictionaries from an internal chunk stream.

    Text is forwarded incrementally. Tool-call deltas are buffered and emitted
    as complete ``tool_use`` blocks, which keeps argument JSON valid.
    """
    message_id = _new_message_id()
    model = request.model
    text_started = False
    text_finished = False
    text_parts: list[str] = []
    tool_acc: dict[int, dict[str, Any]] = {}
    started = False

    def message_start() -> dict[str, Any]:
        return {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": _estimate_tokens(
                        _block_text(request.system) if request.system else ""
                    )
                    + sum(
                        _estimate_tokens(_block_text(m.content))
                        for m in request.messages
                    ),
                    "output_tokens": 0,
                },
            },
        }

    async for raw in inner:
        chunk = raw
        if isinstance(chunk, dict):
            if chunk.get("type") == "meta":
                model = chunk.get("model", model)
                continue
            if chunk.get("type") == "content":
                chunk = chunk["data"]

        if isinstance(chunk, dict) and "error" in chunk:
            if not started:
                yield message_start()
            yield {"type": "error", "error": chunk["error"]}
            return

        if not started:
            started = True
            yield message_start()

        deltas = chunk.get("tool_calls") if isinstance(chunk, dict) else None
        if deltas:
            if text_started and not text_finished:
                yield {"type": "content_block_stop", "index": 0}
                text_finished = True
            for delta in deltas:
                index = int(delta.get("index", 0))
                state = tool_acc.setdefault(
                    index,
                    {"id": _new_tool_id(), "name": "", "arguments": ""},
                )
                if delta.get("id"):
                    state["id"] = delta["id"]
                function = delta.get("function") or {}
                if function.get("name"):
                    state["name"] = function["name"]
                if function.get("arguments"):
                    state["arguments"] += function["arguments"]
            continue

        if chunk:
            text = str(chunk)
            if not text_started:
                text_started = True
                yield {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                }
            text_parts.append(text)
            yield {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            }

    if not started:
        yield message_start()

    if text_started and not text_finished:
        yield {"type": "content_block_stop", "index": 0}

    next_index = 1 if text_started else 0
    for index in sorted(tool_acc):
        state = tool_acc[index]
        yield {
            "type": "content_block_start",
            "index": next_index,
            "content_block": {
                "type": "tool_use",
                "id": state["id"],
                "name": state["name"],
                "input": {},
            },
        }
        if state["arguments"]:
            yield {
                "type": "content_block_delta",
                "index": next_index,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": state["arguments"],
                },
            }
        yield {"type": "content_block_stop", "index": next_index}
        next_index += 1

    output_text = "".join(text_parts)
    output_tokens = _estimate_tokens(output_text) + sum(
        _estimate_tokens(state["arguments"]) for state in tool_acc.values()
    )
    yield {
        "type": "message_delta",
        "delta": {
            "stop_reason": "tool_use" if tool_acc else "end_turn",
            "stop_sequence": None,
        },
        "usage": {"output_tokens": output_tokens},
    }
    yield {"type": "message_stop"}
