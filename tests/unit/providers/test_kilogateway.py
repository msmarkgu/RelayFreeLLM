import json
import unittest
from unittest.mock import MagicMock, patch

from ._base import BaseProviderTestMixin
from src.api_clients.kilogateway_client import KiloGatewayClient
from src.config import settings


class _AsyncContextMock:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        return None


class TestKiloGatewayClient(BaseProviderTestMixin, unittest.IsolatedAsyncioTestCase):
    PROVIDER_NAME = "KiloGateway"
    HAS_STREAMING = True

    def _create_client(self):
        self.mock_get = patch("httpx.AsyncClient.get").start()
        self.addCleanup(self.mock_get.stop)
        self.mock_post = patch("httpx.AsyncClient.post").start()
        self.addCleanup(self.mock_post.stop)
        self.mock_stream = patch("httpx.AsyncClient.stream").start()
        self.addCleanup(self.mock_stream.stop)
        self.client = KiloGatewayClient()

    @property
    def _expected_model_ids(self):
        return [
            "kilo-auto/free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "nvidia/nemotron-3.5-super-vl:free",
            "baidu/ernie-5.5-flash-preview:free",
            "nvidia/nemotron-3.5-lightning:free",
        ]

    @property
    def _model_for_test(self):
        return "nvidia/nemotron-3.5-lightning:free"

    def _mock_list_models_success(self):
        self.mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "object": "list",
                "data": [
                    {"id": "kilo-auto/free"},
                    {"id": "nvidia/nemotron-3-ultra-550b-a55b:free"},
                    {"id": "nvidia/nemotron-3.5-super-vl:free"},
                    {"id": "baidu/ernie-5.5-flash-preview:free"},
                    {"id": "nvidia/nemotron-3.5-lightning:free"},
                    {"id": "liquid/lfm-3-1.7b:free"},
                    {"id": "anthropic/claude-sonnet-4.5"},
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
            json=lambda: {"choices": [{"message": {"content": text}}]},
        )

    def _mock_chat_rate_limit(self):
        self.mock_post.return_value = MagicMock(
            status_code=429, text="Anonymous rate limit exceeded"
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
        self.assertEqual(self.client.base_url, "https://ai-gateway.kilo.ai/api/v1")

    async def test_no_api_key_lookup(self):
        with patch.object(
            settings, "get_api_key", side_effect=AssertionError("unexpected key lookup")
        ):
            client = KiloGatewayClient()

        self.assertEqual(client.api_key, "")

    async def test_list_models_is_public_and_free_only(self):
        self._mock_list_models_success()

        models = await self.client.list_models()

        for model in self._expected_model_ids:
            self.assertIn(model, models)
        # Other :free models stay discoverable; the registry curates the top 5.
        self.assertIn("liquid/lfm-3-1.7b:free", models)
        self.assertNotIn("anthropic/claude-sonnet-4.5", models)
        args, kwargs = self.mock_get.await_args
        self.assertEqual(args[0], "https://ai-gateway.kilo.ai/api/v1/models")
        self.assertNotIn("Authorization", kwargs["headers"])

    async def test_chat_requests_are_anonymous(self):
        self._mock_chat_success("Hello")

        await self._call_api(
            messages=[{"role": "user", "content": "Hi"}],
            model=self._model_for_test,
        )

        args, kwargs = self.mock_post.await_args
        self.assertEqual(
            args[0], "https://ai-gateway.kilo.ai/api/v1/chat/completions"
        )
        self.assertNotIn("Authorization", kwargs["headers"])
        self.assertEqual(kwargs["json"]["model"], self._model_for_test)
