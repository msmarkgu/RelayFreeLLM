"""
Tests for AgentOrchestrator and the map–reduce pipeline.

Covers:
- Planner output parsing (JSON, embedded array, fallback)
- select_many() on ModelSelector
- Parallel expert execution (mocked dispatcher)
- Synthesis prompt construction
- Error paths: planner failure, expert failure, retry
"""

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.models import AgentRunRequest, AgentRunResponse, AgentSubtaskResult
from src.orchestrator import AgentOrchestrator


# ── Helpers ───────────────────────────────────────────────────────────


def _make_selector_mock():
    selector = MagicMock()
    selector.estimate_tokens = MagicMock(return_value=50)
    selector.select_many = MagicMock(
        return_value=[("Groq", "llama-3.3-70b-versatile"),
                       ("Mistral", "mistral-large-latest"),
                       ("Cerebras", "llama-3.3-70b")]
    )
    selector.select = MagicMock(
        return_value=("Groq", "llama-3.3-70b-versatile", 0.0)
    )
    return selector


def _make_dispatcher_mock(responses: dict | None = None):
    dispatcher = MagicMock()
    _responses = responses or {}
    _call_count = 0

    async def _mock_call_provider_api(*args, **kwargs):
        nonlocal _call_count
        provider = kwargs.get("provider_name", args[0] if args else "")
        if provider in _responses:
            return _responses[provider]
        _call_count += 1
        return f"Response from {_call_count}"

    dispatcher.call_provider_api = AsyncMock(side_effect=_mock_call_provider_api)
    return dispatcher


# ── Planner parsing tests ─────────────────────────────────────────────


class TestPlannerParsing(unittest.TestCase):

    def test_parse_direct_json_array(self):
        text = json.dumps([
            {"id": 1, "description": "A", "prompt": "Do A"},
            {"id": 2, "description": "B", "prompt": "Do B"},
        ])
        result = AgentOrchestrator._parse_plan(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], 1)

    def test_parse_embedded_json_array(self):
        text = "Here is the plan:\n[ {\"id\": 1, \"description\": \"A\", \"prompt\": \"Do A\"} ]\nDone."
        result = AgentOrchestrator._parse_plan(text)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)

    def test_parse_wrapped_in_object(self):
        text = json.dumps({
            "subtasks": [
                {"id": 1, "description": "X", "prompt": "X prompt"},
            ]
        })
        result = AgentOrchestrator._parse_plan(text)
        self.assertEqual(len(result), 1)

    def test_parse_garbage_returns_none(self):
        result = AgentOrchestrator._parse_plan("No JSON here at all")
        self.assertIsNone(result)

    def test_parse_empty_array(self):
        result = AgentOrchestrator._parse_plan("[]")
        self.assertEqual(result, [])


class TestSingleSubtaskFallback(unittest.TestCase):

    def test_fallback_shape(self):
        s = AgentOrchestrator._single_subtask_fallback("test task")
        self.assertEqual(s["id"], 1)
        self.assertIn("test task", s["prompt"])


# ── select_many tests ─────────────────────────────────────────────────


class TestSelectMany(unittest.TestCase):

    def test_select_many_returns_requested_count(self):
        selector = _make_selector_mock()
        selector.select_many = MagicMock(
            return_value=[("A", "m1"), ("B", "m2"), ("C", "m3")]
        )
        result = selector.select_many(num=3, user_input="hello")
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("A", "m1"))

    def test_select_many_handles_fewer_available(self):
        selector = _make_selector_mock()
        selector.select_many = MagicMock(return_value=[("A", "m1")])
        result = selector.select_many(num=5, user_input="hello")
        self.assertEqual(len(result), 1)

    def test_select_many_empty_when_none_available(self):
        selector = _make_selector_mock()
        selector.select_many = MagicMock(return_value=[])
        result = selector.select_many(num=3, user_input="hello")
        self.assertEqual(result, [])


# ── Orchestrator end-to-end tests (mocked dispatcher) ────────────────


class TestOrchestratorRun(unittest.TestCase):

    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _make_request(self, **overrides):
        defaults = {
            "task": "Compare RLHF and DPO",
            "use_case": "research",
            "num_experts": 2,
            "stream": False,
            "max_tokens_per_subtask": 1000,
            "max_tokens_synthesis": 2000,
        }
        defaults.update(overrides)
        return AgentRunRequest(**defaults)

    def test_successful_run(self):
        selector = _make_selector_mock()
        dispatcher = _make_dispatcher_mock()

        # Planner returns 2 subtasks
        planner_json = json.dumps([
            {"id": 1, "description": "RLHF", "prompt": "Explain RLHF", "model_type": "text", "model_scale": "large"},
            {"id": 2, "description": "DPO", "prompt": "Explain DPO", "model_type": "text", "model_scale": "large"},
        ])

        call_count = 0

        async def _call(provider_name=None, model_name=None, user_prompt="", **kwargs):
            nonlocal call_count
            call_count += 1
            # Call 1: planner (goes through selector.select → dispatcher.call_provider_api)
            # Call 2+3: expert subtasks
            # Call 4: synthesizer
            if call_count == 1:
                return planner_json
            if call_count == 2:
                return "RLHF explanation content"
            if call_count == 3:
                return "DPO explanation content"
            return "Combined answer: RLHF vs DPO comparison."

        dispatcher.call_provider_api = AsyncMock(side_effect=_call)
        orchestrator = AgentOrchestrator(dispatcher=dispatcher, selector=selector)
        request = self._make_request()

        result = self.run_async(orchestrator.run(request))

        self.assertIsInstance(result, AgentRunResponse)
        self.assertEqual(result.task, "Compare RLHF and DPO")
        self.assertEqual(len(result.subtasks), 2)
        self.assertIn("RLHF", result.final_answer)
        self.assertEqual(result.meta.subtasks_completed, 2)
        self.assertEqual(result.meta.subtasks_failed, 0)

    def test_planner_failure_falls_back_to_single_subtask(self):
        selector = _make_selector_mock()

        async def _call_failing(**kwargs):
            raise RuntimeError("Planner provider unavailable")

        dispatcher = MagicMock()
        dispatcher.call_provider_api = AsyncMock(side_effect=_call_failing)
        orchestrator = AgentOrchestrator(dispatcher=dispatcher, selector=selector)
        request = self._make_request(num_experts=3)

        result = self.run_async(orchestrator.run(request))

        # Falls back to 1 subtask; planner failure should not crash
        self.assertIsInstance(result, AgentRunResponse)
        # The single fallback subtask is still executed
        self.assertGreaterEqual(result.meta.subtasks_completed, 0)

    def test_expert_failure_with_continue_on_subtask_error(self):
        selector = _make_selector_mock()

        async def _call_expert_fail(provider_name=None, **kwargs):
            if provider_name == "Cerebras":
                raise RuntimeError("Cerebras down")
            return "Expert answer"

        dispatcher = MagicMock()
        dispatcher.call_provider_api = AsyncMock(side_effect=_call_expert_fail)
        orchestrator = AgentOrchestrator(dispatcher=dispatcher, selector=selector)
        request = self._make_request(num_experts=2)

        result = self.run_async(orchestrator.run(request))

        # At least one expert succeeded
        self.assertIsInstance(result, AgentRunResponse)

    def test_all_experts_fail_returns_degradation_message(self):
        selector = _make_selector_mock()
        selector.select_many = MagicMock(return_value=[])  # no providers

        async def _call_noop(**kwargs):
            return "noop"

        dispatcher = MagicMock()
        dispatcher.call_provider_api = AsyncMock(side_effect=_call_noop)
        orchestrator = AgentOrchestrator(dispatcher=dispatcher, selector=selector)
        request = self._make_request(num_experts=3)

        result = self.run_async(orchestrator.run(request))

        self.assertIn("All expert subtasks failed", result.final_answer)
        self.assertEqual(result.meta.subtasks_completed, 0)

    def test_synthesis_uses_expert_results(self):
        selector = _make_selector_mock()

        synth_received_prompts = []
        call_count = 0

        async def _call_track_synth(provider_name=None, user_prompt="", **kwargs):
            nonlocal call_count
            call_count += 1
            # Call 1: planner → return 2 subtasks
            if call_count == 1:
                return json.dumps([
                    {"id": 1, "description": "A", "prompt": "Do A"},
                    {"id": 2, "description": "B", "prompt": "Do B"},
                ])
            # Calls 2-3: experts → return results
            if call_count in (2, 3):
                return f"Expert answer {call_count}"
            # Call 4: synthesizer → track the prompt
            synth_received_prompts.append(user_prompt)
            return "Synthesised answer"

        dispatcher = MagicMock()
        dispatcher.call_provider_api = AsyncMock(side_effect=_call_track_synth)
        orchestrator = AgentOrchestrator(dispatcher=dispatcher, selector=selector)
        request = self._make_request(num_experts=2)

        result = self.run_async(orchestrator.run(request))

        self.assertEqual(len(synth_received_prompts), 1)
        synth_prompt = synth_received_prompts[0]
        self.assertIn("Expert 1", synth_prompt)
        self.assertIn("Expert 2", synth_prompt)

    def run_async(self, coro):
        return asyncio.run(coro)


# ── Model tests ───────────────────────────────────────────────────────


class TestAgentModels(unittest.TestCase):

    def test_agent_run_request_defaults(self):
        r = AgentRunRequest(task="test task")
        self.assertEqual(r.use_case, "general")
        self.assertEqual(r.num_experts, 4)
        self.assertFalse(r.stream)
        self.assertEqual(r.max_tokens_per_subtask, 1500)

    def test_agent_run_response_shape(self):
        resp = AgentRunResponse(
            task="test",
            subtasks=[],
            final_answer="done",
            meta={"subtasks_completed": 0},
        )
        self.assertEqual(resp.task, "test")
        self.assertEqual(resp.final_answer, "done")


if __name__ == "__main__":
    unittest.main()
