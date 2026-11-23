"""Gateway error envelopes, HTTP statuses and token reporting."""

import json
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.models import build_error_response, build_response
from src.router import api_router


class FakeSelector:
    def estimate_tokens(self, text: str) -> int:
        return len(text.split())


class FakeDispatcher:
    async def chat(self, request, **kwargs):
        if request.model == "rate-limited":
            return build_error_response("rate limited", 1, "rate_limit_error")
        if request.model == "bad-request":
            return build_error_response("bad input", 1, "invalid_request_error")
        if request.stream:
            if request.model == "stream-error":
                async def broken():
                    yield "partial"
                    raise RuntimeError("upstream died")
                return broken()

            async def stream():
                yield "hello"
                yield " world"
            return stream()

        return build_response(
            "hello world", "Gemini", "gemini-2.5-flash", 1.0, 1,
            prompt_tokens=2, completion_tokens=2,
        )


class TestErrorAndUsage(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(api_router)
        self.app.state.dispatcher = FakeDispatcher()
        self.app.state.selector = FakeSelector()
        self.app.state.usage_tracker = None
        self.client = TestClient(self.app)

    def post(self, payload: dict):
        return self.client.post("/v1/chat/completions", json=payload)

    def test_non_stream_usage_is_populated(self):
        response = self.post({
            "messages": [{"role": "user", "content": "hi there"}],
            "model": "meta-model",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["usage"]["total_tokens"], 4)

    def test_rate_limit_returns_429_envelope(self):
        response = self.post({
            "messages": [{"role": "user", "content": "hi"}],
            "model": "rate-limited",
        })
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["type"], "rate_limit_error")

    def test_invalid_request_returns_400_envelope(self):
        response = self.post({
            "messages": [{"role": "user", "content": "hi"}],
            "model": "bad-request",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["type"], "invalid_request_error")

    def test_stream_final_chunk_carries_usage(self):
        response = self.post({
            "messages": [{"role": "user", "content": "hi there"}],
            "model": "meta-model",
            "stream": True,
        })
        self.assertEqual(response.status_code, 200)
        frames = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        self.assertTrue(any(f.get("usage", {}).get("total_tokens", 0) > 0 for f in frames))

    def test_mid_stream_failure_emits_error_event(self):
        response = self.post({
            "messages": [{"role": "user", "content": "hi"}],
            "model": "stream-error",
            "stream": True,
        })
        self.assertIn('"type": "streaming_error"', response.text)
        self.assertNotIn('"finish_reason": "error"', response.text)


if __name__ == "__main__":
    unittest.main()
