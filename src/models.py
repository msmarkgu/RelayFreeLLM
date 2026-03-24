"""
Pydantic models for the RelayLLMs Meta Model.

Provides OpenAI-compatible request/response types so the router
can be used as a drop-in replacement for OpenAI's /v1/chat/completions.
"""

import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Request Models ──────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: Literal["system", "user", "assistant"]
    content: str


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

    def get_system_prompt(self) -> str:
        """Extract the system prompt from messages, if any."""
        for msg in self.messages:
            if msg.role == "system":
                return msg.content
        return ""

    def get_user_prompt(self) -> str:
        """Extract the last user message."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.content
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
    content: str


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
