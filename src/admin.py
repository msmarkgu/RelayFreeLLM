"""
Admin dashboard routes for RelayFreeLLM.

Provides a web UI and REST API for managing provider model limits
and viewing usage statistics. All data is persisted to JSON files.
"""

import json
import os
import mimetypes

from fastapi import APIRouter, Header, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .logging_util import ProjectLogger

CUR_DIR = os.path.dirname(os.path.realpath(__file__))
STATIC_DIR = os.path.join(CUR_DIR, "static")
LIMITS_FILE = os.path.join(CUR_DIR, "provider_model_limits.json")

admin_router = APIRouter()
logger = ProjectLogger.get_logger(__name__)

mimetypes.init()


@admin_router.get("/static/{filename}")
async def serve_static(filename: str):
    filepath = os.path.join(STATIC_DIR, filename)
    if not os.path.isfile(filepath) or ".." in filename:
        raise HTTPException(status_code=404, detail="Not found")
    content_type, _ = mimetypes.guess_type(filename)
    with open(filepath, "r") as f:
        return Response(content=f.read(), media_type=content_type or "text/plain")


@admin_router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard():
    html_path = os.path.join(CUR_DIR, "static", "admin.html")
    try:
        with open(html_path, "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Admin dashboard not found")


@admin_router.get("/chat", response_class=HTMLResponse)
async def chat_ui():
    html_path = os.path.join(CUR_DIR, "static", "chat.html")
    try:
        with open(html_path, "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Chat UI not found")


@admin_router.get("/admin/api/limits")
async def get_limits():
    try:
        with open(LIMITS_FILE, "r") as f:
            return JSONResponse(content=json.load(f))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read limits: {e}")


@admin_router.put("/admin/api/limits")
async def update_limits(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict) or "providers" not in body:
        raise HTTPException(status_code=400, detail="Payload must contain a 'providers' array")

    for prov in body["providers"]:
        if "name" not in prov:
            raise HTTPException(status_code=400, detail="Each provider must have a 'name'")
        if "models" not in prov or not isinstance(prov["models"], list):
            raise HTTPException(status_code=400, detail=f"Provider '{prov.get('name')}' must have a 'models' array")

        for model in prov["models"]:
            if "name" not in model:
                raise HTTPException(status_code=400, detail="Each model must have a 'name'")
            if "limits" not in model or not isinstance(model["limits"], dict):
                raise HTTPException(status_code=400, detail=f"Model '{model.get('name')}' must have a 'limits' object")

    try:
        with open(LIMITS_FILE, "w") as f:
            json.dump(body, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write limits: {e}")

    try:
        selector = request.app.state.selector
        if selector:
            new_providers = selector.load_api_limits_from_json(selector.registry_file)
            selector.providers.clear()
            selector.providers.update(new_providers)
            selector.provider_sequence = list(new_providers.keys())
            logger.info("Model limits hot-reloaded from admin dashboard")
    except Exception as e:
        logger.error(f"Failed to hot-reload model limits: {e}")

    return JSONResponse(content={"message": "Limits saved and hot-reloaded successfully."})


@admin_router.get("/admin/api/usage")
async def get_usage(request: Request):
    try:
        tracker = request.app.state.usage_tracker
        return JSONResponse(content=tracker.get_stats())
    except AttributeError:
        raise HTTPException(status_code=501, detail="Usage tracking not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read usage: {e}")


@admin_router.post("/admin/api/usage/reset")
async def reset_usage(request: Request):
    try:
        tracker = request.app.state.usage_tracker
        tracker.reset_stats()
        return JSONResponse(content={"message": "Usage stats reset."})
    except AttributeError:
        raise HTTPException(status_code=501, detail="Usage tracking not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset usage: {e}")


# ── Conversation API ────────────────────────────────────────


def get_conversation_store(request: Request):
    store = getattr(request.app.state, "conversation_store", None)
    if not store:
        raise HTTPException(status_code=501, detail="Conversation store not available")
    return store


def get_device_id(x_device_id: str = Header(default="")):
    if not x_device_id:
        raise HTTPException(status_code=400, detail="X-Device-ID header is required")
    return x_device_id


@admin_router.get("/api/conversations")
async def list_conversations(request: Request, device_id: str = Header(default="")):
    try:
        store = get_conversation_store(request)
        if not device_id:
            return JSONResponse(content=[])
        convs = store.list_conversations(device_id)
        return JSONResponse(content=convs)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"list_conversations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/api/conversations")
async def create_conversation(request: Request, device_id: str = Header(default="")):
    try:
        store = get_conversation_store(request)
        if not device_id:
            raise HTTPException(status_code=400, detail="X-Device-ID header is required")
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        model = body.get("model", "meta-model")
        result = store.create_conversation(device_id, model=model)
        return JSONResponse(content=result, status_code=201)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"create_conversation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get("/api/conversations/{conv_id}")
async def get_conversation(request: Request, conv_id: str, device_id: str = Header(default="")):
    try:
        store = get_conversation_store(request)
        if not device_id:
            raise HTTPException(status_code=400, detail="X-Device-ID header is required")
        conv = store.get_conversation(device_id, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return JSONResponse(content=conv)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_conversation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.put("/api/conversations/{conv_id}")
async def update_conversation(request: Request, conv_id: str, device_id: str = Header(default="")):
    try:
        store = get_conversation_store(request)
        if not device_id:
            raise HTTPException(status_code=400, detail="X-Device-ID header is required")
        body = await request.json()
        ok = store.update_conversation(device_id, conv_id, body)
        if not ok:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return JSONResponse(content={"ok": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"update_conversation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.delete("/api/conversations/{conv_id}")
async def delete_conversation(request: Request, conv_id: str, device_id: str = Header(default="")):
    try:
        store = get_conversation_store(request)
        if not device_id:
            raise HTTPException(status_code=400, detail="X-Device-ID header is required")
        ok = store.delete_conversation(device_id, conv_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return JSONResponse(content={"ok": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"delete_conversation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/api/conversations/import")
async def import_conversations(request: Request, device_id: str = Header(default="")):
    try:
        store = get_conversation_store(request)
        if not device_id:
            raise HTTPException(status_code=400, detail="X-Device-ID header is required")
        body = await request.json()
        conversations = body.get("conversations", [])
        result = store.import_conversations(device_id, conversations)
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"import_conversations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
