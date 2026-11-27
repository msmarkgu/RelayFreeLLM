"""
Agents Router — FastAPI endpoints for multi-model orchestration.

POST /v1/agents/run — Map–Reduce task decomposition and synthesis.
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from .logging_util import ProjectLogger
from .models import AgentRunRequest, AgentRunResponse
from .orchestrator import AgentOrchestrator

logger = ProjectLogger.get_logger(__name__)

agents_router = APIRouter(prefix="/v1/agents", tags=["agents"])


@agents_router.post("/run", response_model=AgentRunResponse)
async def agent_run(request: AgentRunRequest, raw_request: Request):
    """
    Execute a Map–Reduce orchestration run.

    The task is decomposed into subtasks by a planner LLM, each subtask
    is dispatched to a different model in parallel, and the results are
    synthesised into a single coherent answer.
    """
    dispatcher = getattr(raw_request.app.state, "dispatcher", None)
    selector = getattr(raw_request.app.state, "selector", None)

    if dispatcher is None or selector is None:
        raise HTTPException(status_code=503, detail="Server not fully initialised.")

    orchestrator = AgentOrchestrator(dispatcher=dispatcher, selector=selector)

    try:
        result = await orchestrator.run(request)
    except Exception as e:
        logger.error(f"Agent orchestration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Orchestration failed: {str(e)}")

    return JSONResponse(content=result.model_dump())
