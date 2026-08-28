"""
Integration tests for the agents /v1/agents/run endpoint.

Uses FastAPI TestClient with mocked provider clients and selector
to verify the HTTP interface without hitting real LLM APIs.

NOTE: These tests are excluded from run_tests.py when the installed
FastAPI and Starlette versions are incompatible (known issue with
fastapi==0.115.2 + starlette>=1.2.0).
"""

import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

try:
    from fastapi.testclient import TestClient
    from src.agents_router import agents_router  # noqa: F401 — may raise at import time
    _HAS_FASTAPI_ROUTER = True
except (ImportError, TypeError):
    _HAS_FASTAPI_ROUTER = False

_skip_reason = (
    "FastAPI/Starlette version incompatibility — "
    "APIRouter() raises TypeError at import time. "
    "Skipped until requirements.txt pins compatible versions."
)

from src.models import AgentRunRequest


# ── Helpers ───────────────────────────────────────────────────────────


def _make_mock_dispatcher():
    dispatcher = MagicMock()
    # Planner call count
    _call_n = 0

    async def _call(provider_name=None, model_name=None, user_prompt="", **kwargs):
        nonlocal _call_n
        _call_n += 1
        if _call_n == 1:
            # Planner output
            return json.dumps([
                {"id": 1, "description": "Subtask A", "prompt": "Do A"},
                {"id": 2, "description": "Subtask B", "prompt": "Do B"},
            ])
        if _call_n == 2:
            return "Expert A result: detailed analysis"
        if _call_n == 3:
            return "Expert B result: alternate analysis"
        # Synthesis
        return "Combined answer combining both analyses."

    dispatcher.call_provider_api = AsyncMock(side_effect=_call)
    return dispatcher


def _make_mock_selector():
    selector = MagicMock()
    selector.estimate_tokens = MagicMock(return_value=50)
    selector.select_many = MagicMock(
        return_value=[("Groq", "llama-3.3-70b-versatile"),
                       ("Mistral", "mistral-large-latest")]
    )
    selector.select = MagicMock(
        return_value=("Groq", "llama-3.3-70b-versatile", 0.0)
    )
    return selector


def _build_app():
    """Build a minimal FastAPI app with just the agents router."""
    from fastapi import FastAPI
    from src.agents_router import agents_router

    app = FastAPI()
    app.include_router(agents_router)
    return app


def _wire_app_state(app, dispatcher=None, selector=None):
    """Attach mock objects to app.state."""
    app.state.dispatcher = dispatcher or _make_mock_dispatcher()
    app.state.selector = selector or _make_mock_selector()


# ── Tests ─────────────────────────────────────────────────────────────


@unittest.skipUnless(_HAS_FASTAPI_ROUTER, _skip_reason)
class TestAgentsEndpoint(unittest.TestCase):

    def setUp(self):
        self.app = _build_app()
        _wire_app_state(self.app)
        self.client = TestClient(self.app)

    def test_successful_run_returns_200(self):
        payload = {
            "task": "Compare RLHF and DPO alignment methods",
            "use_case": "research",
            "num_experts": 2,
        }
        resp = self.client.post("/v1/agents/run", json=payload)
        self.assertEqual(resp.status_code, 200)

    def test_successful_run_shape(self):
        payload = {
            "task": "Explain transformers",
            "num_experts": 2,
        }
        resp = self.client.post("/v1/agents/run", json=payload)
        body = resp.json()

        self.assertIn("task", body)
        self.assertIn("subtasks", body)
        self.assertIn("final_answer", body)
        self.assertIn("meta", body)
        self.assertEqual(body["task"], "Explain transformers")
        self.assertIsInstance(body["subtasks"], list)
        self.assertIsInstance(body["final_answer"], str)

    def test_meta_fields_present(self):
        payload = {"task": "test", "num_experts": 2}
        resp = self.client.post("/v1/agents/run", json=payload)
        meta = resp.json()["meta"]

        self.assertIn("subtasks_completed", meta)
        self.assertIn("subtasks_failed", meta)
        self.assertIn("latency_ms", meta)
        self.assertGreaterEqual(meta["subtasks_completed"], 0)

    def test_empty_task_still_runs(self):
        """An empty task should not crash — the planner handles it."""
        payload = {"task": "", "num_experts": 1}
        resp = self.client.post("/v1/agents/run", json=payload)
        self.assertEqual(resp.status_code, 200)

    def test_num_experts_one(self):
        payload = {"task": "single expert", "num_experts": 1}
        resp = self.client.post("/v1/agents/run", json=payload)
        self.assertEqual(resp.status_code, 200)

    def test_missing_task_field_returns_422(self):
        resp = self.client.post("/v1/agents/run", json={})
        self.assertEqual(resp.status_code, 422)

    def test_invalid_num_experts_returns_422(self):
        resp = self.client.post("/v1/agents/run", json={
            "task": "test",
            "num_experts": 0,
        })
        self.assertEqual(resp.status_code, 422)

    def test_num_experts_too_large_returns_422(self):
        resp = self.client.post("/v1/agents/run", json={
            "task": "test",
            "num_experts": 9,
        })
        self.assertEqual(resp.status_code, 422)


@unittest.skipUnless(_HAS_FASTAPI_ROUTER, _skip_reason)
class TestAgentsEndpointNoProviders(unittest.TestCase):
    """When no providers are available, the endpoint should degrade gracefully."""

    def setUp(self):
        self.app = _build_app()
        selector = _make_mock_selector()
        selector.select_many = MagicMock(return_value=[])
        selector.select = MagicMock(side_effect=RuntimeError("No providers"))
        _wire_app_state(self.app, selector=selector)
        self.client = TestClient(self.app)

    def test_all_experts_fail_returns_degradation(self):
        payload = {"task": "test", "num_experts": 2}
        resp = self.client.post("/v1/agents/run", json=payload)
        # Should not crash — should return 200 with degradation message
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("All expert subtasks failed", body["final_answer"])


@unittest.skipUnless(_HAS_FASTAPI_ROUTER, _skip_reason)
class TestAgentsEndpointPlannerFailure(unittest.TestCase):
    """When the planner fails, the orchestrator falls back to a single subtask."""

    def setUp(self):
        self.app = _build_app()
        dispatcher = MagicMock()
        selector = _make_mock_selector()

        async def _call_failing(**kwargs):
            raise RuntimeError("Planner provider unavailable")

        dispatcher.call_provider_api = AsyncMock(side_effect=_call_failing)
        _wire_app_state(self.app, dispatcher=dispatcher, selector=selector)
        self.client = TestClient(self.app)

    def test_planner_failure_does_not_crash(self):
        payload = {"task": "test", "num_experts": 3}
        resp = self.client.post("/v1/agents/run", json=payload)
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
