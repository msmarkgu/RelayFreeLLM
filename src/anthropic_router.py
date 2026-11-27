"""Anthropic Messages API endpoints for Claude Code and compatible harnesses."""

import json
import traceback

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .anthropic_adapter import (
    MessagesRequest,
    count_request_tokens,
    error_payload,
    from_chat_response,
    stream_anthropic_events,
    to_chat_request,
)
from .config import settings
from .logging_util import ProjectLogger
from .models import ChatCompletionResponse

logger = ProjectLogger.get_logger(__name__)

anthropic_router = APIRouter(prefix="/v1/messages", tags=["anthropic"])

ANTHROPIC_STATUS_BY_TYPE = {
    "invalid_request_error": 400,
    "authentication_error": 401,
    "rate_limit_error": 429,
    "server_error": 500,
    "upstream_error": 502,
}


def _resolve_internal_model(requested: str) -> tuple[str, str | None]:
    """Map a Claude tier alias to a concrete provider/model pair."""
    mapped = settings.CLAUDE_MODEL_MAP.get(requested)
    if mapped:
        return mapped, requested
    return settings.META_MODEL_NAME, None


@anthropic_router.post("", response_model=None)
async def create_message(request: Request):
    """Anthropic-compatible POST /v1/messages."""
    try:
        body = await request.json()
        message_request = MessagesRequest(**body)
        internal_request = to_chat_request(message_request)
        internal_request.model, _ = _resolve_internal_model(message_request.model)

        dispatcher = request.app.state.dispatcher
        result = await dispatcher.chat(
            internal_request,
            session_id=request.headers.get(settings.SESSION_ID_HEADER, "default"),
            # Anthropic clients own their system prompt and tool_result blocks.
            use_server_side_system_prompt=False,
        )
    except Exception as ex:
        logger.error(f"messages request error: {ex}\n{traceback.format_exc()}")
        return JSONResponse(
            error_payload(str(ex), "invalid_request_error"), status_code=400
        )

    if isinstance(result, ChatCompletionResponse) and result.error:
        return JSONResponse(
            error_payload(result.error.message, result.error.type),
            status_code=ANTHROPIC_STATUS_BY_TYPE.get(result.error.type, 500),
        )

    if message_request.stream:
        async def event_stream():
            try:
                async for event in stream_anthropic_events(result, message_request):
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            except Exception as ex:
                logger.error(f"messages stream error: {ex}\n{traceback.format_exc()}")
                yield (
                    f"event: error\ndata: {json.dumps(error_payload(str(ex)))}\n\n"
                )

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return JSONResponse(from_chat_response(result, message_request.model))


@anthropic_router.post("/count_tokens", response_model=None)
async def count_tokens(request: Request):
    """Anthropic-compatible token counting for prompt budgeting."""
    try:
        body = await request.json()
        message_request = MessagesRequest(**body)
        return JSONResponse({"input_tokens": count_request_tokens(message_request)})
    except Exception as ex:
        return JSONResponse(
            error_payload(str(ex), "invalid_request_error"), status_code=400
        )
