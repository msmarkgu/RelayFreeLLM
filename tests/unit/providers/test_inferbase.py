import json
import unittest
from unittest.mock import MagicMock, patch

from ._base import BaseProviderTestMixin
from src.api_clients.inferbase_client import InferbaseClient
from src.api_clients.tool_support import ToolResponse
from src.config import settings
from src.exceptions import RateLimitError


class _AsyncContextMock:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        return None


class TestInferbaseClient(BaseProviderTestMixin, unittest.IsolatedAsyncioTestCase):
    PROVIDER_NAME = "Inferbase"
    HAS_STREAMING = True

    def _create_client(self):
        self.mock_get = patch("httpx.AsyncClient.get").start()
        self.addCleanup(self.mock_get.stop)
        self.mock_post = patch("httpx.AsyncClient.post").start()
        self.addCleanup(self.mock_post.stop)
        self.mock_stream = patch("httpx.AsyncClient.stream").start()
        self.addCleanup(self.mock_stream.stop)
        self.client = InferbaseClient()

    @property
    def _expected_model_ids(self):
        return [
            "auto",
            "deepseek-v4-flash",
            "openai-gpt-oss-120b",
            "qwen3-coder-480b-a35b-instruct",
            "zai-glm-4-7",
        ]

    @property
    def _model_for_test(self):
        return "auto"

    def _mock_list_models_success(self):
        self.mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "object": "list",
                "data": [
                    {
                        "id": model,
                        "supported_parameters": ["tools", "tool_choice", "stream"],
                    }
                    for model in self._expected_model_ids
                ],
            },
        )

    def _mock_list_models_empty(self):
        self.mock_get.return_value = MagicMock(
            status_code=200, json=lambda: {"data": []}
        )

    def _mock_list_models_error(self):
        self.mock_get.return_value = MagicMock(status_code=500, text="error")

    def _mock_chat_success(self, text):
        self.mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "object": "chat.completion",
                "model": "deepseek-v4-flash",
                "choices": [{"message": {"content": text}}],
            },
        )

    def _mock_chat_rate_limit(self):
        self.mock_post.return_value = MagicMock(
            status_code=429,
            text='{"error":{"message":"Free plan capacity reached","code":"free_plan_capacity"}}',
        )

    def _mock_chat_auth_error(self):
        self.mock_post.return_value = MagicMock(status_code=401, text="Unauthorized")

    def _mock_chat_provider_error(self):
        self.mock_post.return_value = MagicMock(
            status_code=500, text="Internal server error"
        )

    def _set_stream_lines(self, lines):
        response = MagicMock(status_code=200)
        response.aiter_lines = lambda: self._async_lines(lines)
        self.mock_stream.return_value = _AsyncContextMock(response)

    async def _async_lines(self, lines):
        for line in lines:
            yield line

    def _mock_chat_stream(self, chunks):
        lines = [
            "data: " + json.dumps({"choices": [{"delta": {"content": chunk}}]})
            for chunk in chunks
        ]
        lines.append("data: [DONE]")
        self._set_stream_lines(lines)

    async def test_base_url(self):
        self.assertEqual(self.client.base_url, "https://api.inferbase.ai/v1")

    async def test_model_catalog_is_public(self):
        self._mock_list_models_success()

        models = await self.client.list_models()

        self.assertEqual(models, self._expected_model_ids)
        args, kwargs = self.mock_get.await_args
        self.assertEqual(args[0], "https://api.inferbase.ai/v1/models")
        self.assertNotIn("Authorization", kwargs["headers"])

    async def test_chat_requests_use_api_key(self):
        self._mock_chat_success("Hello")

        await self._call_api(
            messages=[{"role": "user", "content": "Hi"}],
            model=self._model_for_test,
        )

        args, kwargs = self.mock_post.await_args
        self.assertEqual(
            args[0], "https://api.inferbase.ai/v1/chat/completions"
        )
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")

    async def test_free_plan_limit_maps_to_rate_limit(self):
        self.mock_post.return_value = MagicMock(
            status_code=402,
            text='{"error":{"message":"Daily free-plan limit reached","code":"free_plan_limit"}}',
        )

        with self.assertRaises(RateLimitError):
            await self._call_api(
                messages=[{"role": "user", "content": "Hi"}],
                model=self._model_for_test,
            )

    async def test_tool_calls_are_returned(self):
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "read_file", "arguments": '{"path":"a.py"}'},
        }
        self.mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"content": None, "tool_calls": [tool_call]}}]
            },
        )

        result = await self.client.call_model_api(
            messages=[{"role": "user", "content": "Hi"}],
            model=self._model_for_test,
            tools=[
                {
                    "type": "function",
                    "function": {"name": "read_file", "parameters": {}},
                }
            ],
            tool_choice="auto",
        )

        self.assertIsInstance(result, ToolResponse)
        self.assertEqual(result.content, "")
        self.assertEqual(result.tool_calls, [tool_call])

    async def test_streamed_tool_call_deltas_and_routing_event(self):
        lines = [
            'data: {"object":"routing","decision":{"model":"deepseek-v4-flash"}}',
            "data: " + json.dumps({
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path":"a.py"}',
                            },
                        }]
                    }
                }]
            }),
            "data: [DONE]",
        ]
        self._set_stream_lines(lines)

        generator = await self.client.call_model_api(
            messages=[{"role": "user", "content": "Hi"}],
            model=self._model_for_test,
            stream=True,
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        )
        chunks = [chunk async for chunk in generator]

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["tool_calls"][0]["id"], "call_1")

    async def test_api_key_required(self):
        with patch.object(settings, "get_api_key", side_effect=ValueError("missing")):
            with self.assertRaises(ValueError):
                InferbaseClient()
