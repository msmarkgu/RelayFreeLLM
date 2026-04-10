"""
AIModelRouter — Meta Model Server

Entry point for the FastAPI application.
Initializes shared instances (registry, selector, dispatcher) on startup
and makes them available to routes via app.state.
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .config import settings
from .logging_util import ProjectLogger
from .model_dispatcher import ModelDispatcher
from .model_selector import ModelSelector
from .provider_registry import ProviderRegistry
from .usage_tracker import UsageTracker
from .router import api_router

# Configure logging early
ProjectLogger.configure(
    project_name="RelayFreeLLM",
    log_dir="logs",
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
)
logger = ProjectLogger.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for shared state."""
    logger.info("=== RelayFreeLLM starting up ===")

    # 1. Auto-discover provider clients (This asserts Python code & API keys are valid)
    registry = ProviderRegistry()
    registry.auto_discover()

    # 2. Initialize model selector (This asserts limits exist in JSON)
    selector = ModelSelector()

    # --- SYNCHRONIZE AND VALIDATE ---
    registered_providers = set(registry.list_providers())
    json_providers = set(selector.providers.keys())

    active_providers = registered_providers.intersection(json_providers)

    # Scour out unsupported providers
    for p in list(registered_providers):
        if p not in active_providers:
            logger.warning(f"Provider '{p}' has credentials/code but lacks JSON limits! Pruning.")
            registry.unregister(p)

    for p in list(json_providers):
        if p not in active_providers:
            logger.warning(f"Provider '{p}' has JSON limits but lacks credentials/code! Pruning.")
            selector.remove_provider(p)

    # ABORT IF EMPTY
    if len(active_providers) == 0:
        logger.critical("No valid providers registered (check .env and JSON limits)! Aborting server startup.")
        sys.exit(1)

    # 3. Initialize usage tracker (persisted stats)
    usage_tracker = UsageTracker()

    # 4. Create the dispatcher (the meta model core)
    dispatcher = ModelDispatcher(
        registry=registry, 
        selector=selector, 
        usage_tracker=usage_tracker
    )

    # Inject into app.state so routes can access them
    app.state.registry = registry
    app.state.selector = selector
    app.state.dispatcher = dispatcher
    app.state.usage_tracker = usage_tracker

    logger.info(
        f"Meta model '{settings.META_MODEL_NAME}' ready with providers: "
        f"{registry.list_providers()}"
    )

    yield  # app is running

    logger.info("=== RelayFreeLLM shutting down ===")


app = FastAPI(
    title="RelayFreeLLM — Meta Model",
    description="A unified LLM endpoint that transparently routes across multiple AI providers.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(api_router)


if __name__ == "__main__":
    uvicorn.run(
        app,
        port=settings.PORT,
        host=settings.HOST,
    )
