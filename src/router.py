"""
API routes for the RelayFreeLLM meta model.

Provides an OpenAI-compatible /v1/chat/completions gateway.
"""

import datetime
import json
import logging
import os
import traceback

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from starlette.responses import Response, JSONResponse
from uuid import uuid4

from .config import settings
from .models import ChatCompletionRequest, ChatCompletionResponse, ErrorDetail
from .logging_util import ProjectLogger

CUR_DIR = os.path.dirname(os.path.realpath(__file__))
CUR_FILE = os.path.basename(__file__)
TODAY = datetime.datetime.today().strftime("%Y-%m-%d")

api_router = APIRouter()

# Configure project-wide logging (only once)
ProjectLogger.configure(project_name="RelayFreeLLM", log_dir="logs", level=logging.INFO)

logger = ProjectLogger.get_logger(__name__)

# Gateway error types map to real HTTP statuses so client retry logic works.
ERROR_STATUS_BY_TYPE = {
    "invalid_request_error": 400,
    "authentication_error": 401,
    "rate_limit_error": 429,
    "server_error": 500,
    "upstream_error": 502,
}


def _error_response(
    error: ErrorDetail, status_code: int | None = None
) -> JSONResponse:
    """Return an OpenAI-shaped error envelope with a meaningful HTTP status."""
    return JSONResponse(
        status_code=status_code or ERROR_STATUS_BY_TYPE.get(error.type, 500),
        content={"error": {"message": error.message, "type": error.type}},
    )


# ── Dependency ──────────────────────────────────────────────────────
# The dispatcher is injected by server.py via app.state


def get_dispatcher(request: Request):
    return request.app.state.dispatcher


def get_selector(request: Request):
    return request.app.state.selector


def get_usage_tracker(request: Request):
    return request.app.state.usage_tracker


def _parse_bool_header(value: str | None) -> bool | None:
    """Parse a boolean HTTP header value. Returns None if absent or invalid."""
    if value is None:
        return None
    stripped = value.strip().lower()
    if stripped == "true":
        return True
    if stripped == "false":
        return False
    return None


# ── Health ──────────────────────────────────────────────────────────


@api_router.get("/")
def health() -> Response:
    return Response(content="Healthy", status_code=200)


@api_router.get("/health")
def health_detail() -> JSONResponse:
    """Detailed health check."""
    return JSONResponse(
        content={
            "status": "healthy",
            "meta_model": settings.META_MODEL_NAME,
            "providers": get_provider_list_from_state(),
        },
        status_code=200,
    )


def get_provider_list_from_state():
    """Helper — returns provider list if app state exists."""
    try:
        from .server import app

        return app.state.registry.list_providers()
    except Exception:
        return []


# ── OpenAI-Compatible Endpoints (Primary) ──────────────────────────


@api_router.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
    """
    OpenAI-compatible chat completions endpoint.

    Users interact with this as if talking to a single AI model.
    The router transparently selects the best available provider.
    """
    try:
        body = await request.json()
        chat_request = ChatCompletionRequest(**body)
        dispatcher = get_dispatcher(request)

        # Read session ID from header (used by context manager for per-session history)
        session_id = request.headers.get(settings.SESSION_ID_HEADER, "default")

        # Read per-request override for USE_SERVER_SIDE_SYSTEM_PROMPT.
        # Absent/invalid header → None → falls back to server default.
        raw = request.headers.get(settings.USE_SERVER_SIDE_SYSTEM_PROMPT_HEADER)
        use_server_side_system_prompt = _parse_bool_header(raw)

        # Extract conversation history (all messages except the last user message).
        # Done here — before the stream/non-stream split — so both paths share it.
        conversation_history = []
        if len(chat_request.messages) > 1:
            conversation_history = chat_request.messages[:-1]

        # Resolve once for both paths. A failure returned as a response object
        # can then become a real HTTP error before SSE bytes are sent.
        dispatch_result = await dispatcher.chat(
            chat_request,
            conversation_history=conversation_history,
            session_id=session_id,
            use_server_side_system_prompt=use_server_side_system_prompt,
        )
        if (
            isinstance(dispatch_result, ChatCompletionResponse)
            and dispatch_result.error
        ):
            return _error_response(dispatch_result.error)

        if not chat_request.stream:
            return JSONResponse(content=dispatch_result.model_dump(), status_code=200)

        # Handle Streaming
        async def stream_generator():
            chat_id = f"chatcmpl-{uuid4().hex[:12]}"
            created = int(datetime.datetime.now().timestamp())
            actual_provider = chat_request.model
            actual_model = chat_request.model
            generated: list[str] = []

            try:
                async for chunk in dispatch_result:
                    # Handle metadata dict from dispatcher's _stream_with_meta
                    if isinstance(chunk, dict):
                        if chunk.get("type") == "meta":
                            actual_provider = chunk["provider"]
                            actual_model = chunk["model"]
                            continue
                        if chunk.get("type") == "content":
                            chunk = chunk["data"]

                    generated.append(str(chunk))
                    data = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": actual_model,
                        "provider": actual_provider,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": chunk},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(data)}\n\n"

                # OpenAI-compatible final chunk carrying estimated usage.
                selector = get_selector(request)
                prompt_tokens = selector.estimate_tokens(
                    chat_request.get_user_prompt()
                )
                completion_tokens = selector.estimate_tokens("".join(generated))
                usage_chunk = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": actual_model,
                    "provider": actual_provider,
                    "choices": [],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                }
                yield f"data: {json.dumps(usage_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            except Exception as e:
                logger.error(f"Streaming error: {e}\n{traceback.format_exc()}")
                error_data = {
                    "error": {"message": str(e), "type": "streaming_error"},
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    except Exception as ex:
        logger.error(f"chat_completions error: {ex}\n{traceback.format_exc()}")
        return _error_response(
            ErrorDetail(message=f"Error: {ex}", type="server_error"), status_code=500
        )


@api_router.get("/v1/models")
async def list_models_openai(
    request: Request,
    type: str | None = None,
    scale: str | None = None,
) -> JSONResponse:
    """
    OpenAI-compatible model listing with optional type/scale filtering.

    Query params:
        type: Filter by model type (text, coding, image, speech, embedding, moderation, ocr)
        scale: Filter by model scale (large, medium, small)

    Returns "meta-model" as the primary model, plus all
    available underlying provider models.
    """
    try:
        selector = get_selector(request)
        available = selector.get_available_models(model_type=type, model_scale=scale)

        model_list = [
            {
                "id": settings.META_MODEL_NAME,
                "object": "model",
                "owned_by": "relay-llms",
                "description": "Unified meta model — automatically routes to the best available provider.",
            }
        ]

        statuses = selector.get_model_statuses()
        for provider_info in available.get("models", []):
            prov_name = provider_info["provider"]
            for model in provider_info.get("models", []):
                model_name = model["name"]
                status_info = statuses.get(prov_name, {}).get(model_name, {})

                model_list.append(
                    {
                        "id": f"{prov_name}/{model_name}",
                        "object": "model",
                        "owned_by": prov_name,
                        "type": model.get("type", "text"),
                        "scale": model.get("scale", "medium"),
                        "status": status_info.get("status", "available"),
                        "cooldown_remaining_sec": status_info.get(
                            "cooldown_remaining", 0
                        ),
                    }
                )

        return JSONResponse(
            content={
                "object": "list",
                "data": model_list,
            },
            status_code=200,
        )

    except Exception as ex:
        logger.error(f"list_models error: {ex}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error: {ex}")


@api_router.get("/v1/usage")
async def get_usage_v1(request: Request) -> JSONResponse:
    """Get aggregated usage statistics."""
    try:
        tracker = get_usage_tracker(request)
        if not tracker:
            raise HTTPException(status_code=501, detail="Usage tracking not enabled.")
        return JSONResponse(content=tracker.get_stats(), status_code=200)
    except Exception as ex:
        logger.error(f"get_usage error: {ex}")
        raise HTTPException(status_code=500, detail=f"Error: {ex}")
