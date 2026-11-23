"""Anthropic-facing HTTP endpoints used by Claude Code."""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.anthropic_router import anthropic_router
from src.config import settings
from src.models import build_error_response, build_response
from src.router import api_router


class FakeDispatcher:
    def __init__(self):
        self.last_request = None
        self.last_kwargs = {}

    async def chat(self, request, **kwargs):
        self.last_request = request
        self.last_kwargs = kwargs
        if request.model == "bad-model":
            return build_error_response("rate limited", 1, "rate_limit_error")
        if request.stream:
            async def stream():
                yield {"type": "meta", "provider": "Groq", "model": "qwen-3"}
                yield {"type": "content", "data": "Hello"}
            return stream()
        return build_response(
            "Hello",
            provider="Groq",
            model="qwen-3",
            latency_ms=1.0,
            attempt=1,
            prompt_tokens=7,
            completion_tokens=2,
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"x"}'},
            }],
        )


class TestAnthropicEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(api_router)
        self.app.include_router(anthropic_router)
        self.dispatcher = FakeDispatcher()
        self.app.state.dispatcher = self.dispatcher
        self.app.state.selector = None
        self.app.state.usage_tracker = None
        self.client = TestClient(self.app)

    def payload(self, **overrides):
        body = {
            "model": "claude-sonnet-5-5",
            "max_tokens": 128,
            "messages": [{"role": "user", "content": "hi"}],
        }
        body.update(overrides)
        return body

    def test_messages_non_stream(self):
        response = self.client.post("/v1/messages", json=self.payload())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["type"], "message")
        self.assertEqual(body["model"], "claude-sonnet-5-5")
        self.assertEqual(body["stop_reason"], "tool_use")
        self.assertEqual(body["content"][1]["name"], "read_file")
        self.assertEqual(self.dispatcher.last_request.model,
                         settings.CLAUDE_MODEL_MAP["claude-sonnet-5-5"])
        self.assertFalse(self.dispatcher.last_kwargs["use_server_side_system_prompt"])

    def test_messages_stream(self):
        response = self.client.post(
            "/v1/messages", json=self.payload(stream=True)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: message_start", response.text)
        self.assertIn("event: message_stop", response.text)
        self.assertIn("Hello", response.text)

    def test_count_tokens(self):
        response = self.client.post(
            "/v1/messages/count_tokens", json=self.payload()
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["input_tokens"], 0)

    def test_model_discovery_for_claude(self):
        response = self.client.get(
            "/v1/models", headers={"anthropic-version": "2023-06-01"}
        )
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["data"]]
        self.assertIn("claude-sonnet-5-5", ids)

    def test_error_envelope(self):
        with patch.dict(settings.CLAUDE_MODEL_MAP, {"bad-model": "bad-model"}):
            response = self.client.post(
                "/v1/messages", json=self.payload(model="bad-model")
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["type"], "rate_limit_error")


if __name__ == "__main__":
    unittest.main()
