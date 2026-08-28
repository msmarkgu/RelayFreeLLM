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
    """

    role: Literal["system", "user", "assistant"]
    content: Union[str, list[Any]]

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


# ── Agent / Map-Reduce Request/Response ────────────────────────────────


class AgentSubtaskSpec(BaseModel):
    """A single subtask produced by the planner."""

    id: int
    description: str
    model_type: str | None = None   # text, coding, etc. — hints for selection
    model_scale: str | None = None  # large, medium, small
    prompt: str                     # the actual task text sent to the expert


class AgentSubtaskResult(BaseModel):
    """Result of a single expert subtask."""

    id: int
    description: str
    provider: str
    model: str
    result: str


class AgentMetaInfo(BaseModel):
    """Attribution and timing for an agent orchestration run."""

    planner_provider: str | None = None
    planner_model: str | None = None
    synthesizer_provider: str | None = None
    synthesizer_model: str | None = None
    latency_ms: float = 0.0
    subtasks_completed: int = 0
    subtasks_failed: int = 0


class AgentRunRequest(BaseModel):
    """
    Request payload for the /v1/agents/run endpoint.

    The orchestrator decomposes *task* into subtasks using a planner LLM,
    runs each subtask on a different model in parallel, and synthesizes the
    results into *final_answer*.
    """

    task: str
    use_case: Literal["research", "code", "qa", "general"] = "general"
    num_experts: int = Field(default=4, ge=1, le=8)
    stream: bool = False
    max_tokens_per_subtask: int = 1500
    max_tokens_synthesis: int = 3000


class AgentRunResponse(BaseModel):
    """
    Response payload for the /v1/agents/run endpoint.

    Includes the final synthesised answer and per-subtask attribution so
    clients can inspect which provider/model handled each subtask.
    """

    task: str
    subtasks: list[AgentSubtaskResult]
    final_answer: str
    meta: AgentMetaInfo


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
