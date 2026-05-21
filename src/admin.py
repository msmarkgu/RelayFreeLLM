"""
Admin dashboard routes for RelayFreeLLM.

Provides a web UI and REST API for managing provider model limits
and viewing usage statistics. All data is persisted to JSON files.
"""

import json
import os
import mimetypes

from fastapi import APIRouter, Request, HTTPException
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
