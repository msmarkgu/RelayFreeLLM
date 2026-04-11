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
from .models import ChatCompletionRequest
from .logging_util import ProjectLogger

CUR_DIR = os.path.dirname(os.path.realpath(__file__))
CUR_FILE = os.path.basename(__file__)
TODAY = datetime.datetime.today().strftime("%Y-%m-%d")

api_router = APIRouter()

# Configure project-wide logging (only once)
ProjectLogger.configure(project_name="RelayFreeLLM", log_dir="logs", level=logging.INFO)

logger = ProjectLogger.get_logger(__name__)


# ── Dependency ──────────────────────────────────────────────────────
# The dispatcher is injected by server.py via app.state


def get_dispatcher(request: Request):
    return request.app.state.dispatcher


def get_selector(request: Request):
    return request.app.state.selector


def get_usage_tracker(request: Request):
    return request.app.state.usage_tracker


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

        # Extract conversation history (all messages except the last user message).
        # Done here — before the stream/non-stream split — so both paths share it.
        conversation_history = []
        if len(chat_request.messages) > 1:
            conversation_history = chat_request.messages[:-1]

        if not chat_request.stream:
            result = await dispatcher.chat(
                chat_request,
                conversation_history=conversation_history,
                session_id=session_id,
            )
            return JSONResponse(content=result.model_dump(), status_code=200)

        # Handle Streaming
        async def stream_generator():
            chat_id = f"chatcmpl-{uuid4().hex[:12]}"
            created = int(datetime.datetime.now().timestamp())

            try:
                generator = await dispatcher.chat(
                    chat_request,
                    conversation_history=conversation_history,
                    session_id=session_id,
                )

                async for chunk in generator:
                    data = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": chat_request.model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": chunk},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(data)}\n\n"

                yield "data: [DONE]\n\n"

            except Exception as e:
                logger.error(f"Streaming error: {e}\n{traceback.format_exc()}")
                error_data = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": chat_request.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                    "error": {"message": str(e), "type": "streaming_error"},
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    except Exception as ex:
        logger.error(f"chat_completions error: {ex}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error: {ex}")


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
