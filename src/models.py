"""
Pydantic models for the RelayFreeLLM Meta Model.

Provides OpenAI-compatible request/response types so the router
can be used as a drop-in replacement for OpenAI's /v1/chat/completions.
"""

import time
import uuid
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── Request Models ──────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single message in a chat conversation.

    `content` follows the OpenAI Chat Completions spec: either a plain
    string, or a list of structured content parts (e.g. text + image_url).
    Use `get_text()` to flatten to a plain string for downstream consumers
    that don't yet handle structured content.

    Supports OpenAI-specified roles: system, user, assistant, tool, function.
    Contains `tool_calls` and `tool_call_id` for tool use support.
    """

    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Union[str, list[Any]]
    tool_calls: list[dict] = []
    tool_call_id: str = ""

    def get_text(self) -> str:
        """Extract plain text from content.

        Returns the string unchanged when `content` is a string. When
        `content` is a list of content parts, joins the text of every part
        whose `type` is `"text"`. Non-text parts (e.g. `image_url`) are
        skipped. Returns an empty string if no text is extractable.
        """
        if isinstance(self.content, str):
            return self.content
        if not isinstance(self.content, list):
            return ""
        parts = [
            p.get("text", "")
            for p in self.content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return " ".join(parts)


class ResponseFormat(BaseModel):
    """Specificies the output format of the model."""

    type: Literal["text", "json_object"] = "text"


class ChatCompletionRequest(BaseModel):
    """
    OpenAI-compatible chat completion request.

    When model is "meta-model" (default), the router automatically
    selects the best available provider and model.

    Optionally, users can specify model_type and/or model_scale to
    filter the model selection to specific categories.
    """

    model: str = "meta-model"
    messages: list[ChatMessage]
    temperature: float = 0.8
    max_tokens: int = 4000
    stream: bool = False
    response_format: Optional[ResponseFormat] = None
    model_type: Optional[str] = (
        None  # text, coding, image, speech, embedding, moderation, ocr
    )
    model_scale: Optional[str] = None  # large, medium, small
    model_name: Optional[str] = None  # e.g., deepseek, llama

    def get_system_prompt(self) -> str:
        """Extract the system prompt from messages, if any."""
        for msg in self.messages:
            if msg.role == "system":
                return msg.get_text()
        return ""

    def get_user_prompt(self) -> str:
        """Extract the last user message."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.get_text()
        return ""


# ── Response Models ─────────────────────────────────────────────────


class MetaInfo(BaseModel):
    """Extension fields showing which provider/model actually handled the request."""

    provider: str
    model: str
    latency_ms: float
    attempt: int


class ChoiceMessage(BaseModel):
    """The message content within a choice."""

    role: str = "assistant"
    content: str = ""
    tool_calls: list[dict] = []
    tool_call_id: str = ""


class Choice(BaseModel):
    """A single completion choice."""

    index: int = 0
    message: ChoiceMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    """Token usage statistics (estimated)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """
    OpenAI-compatible chat completion response.

    Includes a `meta` extension field with provider/model attribution.
    """

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str  # actual model used (e.g. "gemini-2.5-flash")
    choices: list[Choice]
    usage: Optional[Usage] = None
    meta: MetaInfo  # extension: provider attribution


# ── Helper Factories ────────────────────────────────────────────────


def build_response(
    content: str,
    provider: str,
    model: str,
    latency_ms: float,
    attempt: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> ChatCompletionResponse:
    """Build a ChatCompletionResponse from raw values."""
    if content is None:
        content = ""
    return ChatCompletionResponse(
        model=model,
        choices=[
            Choice(
                message=ChoiceMessage(content=content),
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        meta=MetaInfo(
            provider=provider,
            model=model,
            latency_ms=round(latency_ms, 2),
            attempt=attempt,
        ),
    )


def build_error_response(
    error_message: str,
    attempt: int,
) -> ChatCompletionResponse:
    """Build an error response in the same OpenAI-compatible shape."""
    return ChatCompletionResponse(
        model="none",
        choices=[
            Choice(
                message=ChoiceMessage(content=error_message),
                finish_reason="error",
            )
        ],
        meta=MetaInfo(
            provider="none",
            model="none",
            latency_ms=0,
            attempt=attempt,
        ),
    )
