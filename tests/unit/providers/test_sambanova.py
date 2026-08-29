import unittest
from unittest.mock import MagicMock, patch

from ._base import BaseProviderTestMixin
from src.api_clients.sambanova_client import SambaNovaClient
from src.exceptions import RateLimitError


class TestSambaNovaClient(BaseProviderTestMixin, unittest.IsolatedAsyncioTestCase):
    PROVIDER_NAME = "SambaNova"
    HAS_STREAMING = True

    def _create_client(self):
        self.mock_get = patch("httpx.AsyncClient.get").start()
        self.addCleanup(self.mock_get.stop)
        self.mock_post = patch("httpx.AsyncClient.post").start()
        self.addCleanup(self.mock_post.stop)
        self.mock_stream = patch("httpx.AsyncClient.stream").start()
        self.addCleanup(self.mock_stream.stop)
        self.client = SambaNovaClient()

    @property
    def _expected_model_ids(self):
        return [
            "MiniMax-M2.7",
            "DeepSeek-V3.1",
            "Meta-Llama-3.3-70B-Instruct",
            "gpt-oss-120b",
        ]

    @property
    def _model_for_test(self):
        return "Meta-Llama-3.3-70B-Instruct"

    def _mock_list_models_success(self):
        self.mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "data": [
                    {"id": "MiniMax-M2.7"},
                    {"id": "DeepSeek-V3.1"},
                    {"id": "Meta-Llama-3.3-70B-Instruct"},
                    {"id": "gpt-oss-120b"},
                ]
            },
        )

    def _mock_list_models_empty(self):
        self.mock_get.return_value = MagicMock(
            status_code=200, json=lambda: {"data": []}
        )

    def _mock_list_models_error(self):
        self.mock_get.return_value = MagicMock(status_code=500)

    def _mock_chat_success(self, text):
        self.mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": text}}]},
        )

    def _mock_chat_rate_limit(self):
        self.mock_post.return_value = MagicMock(status_code=429, text="Rate limit exceeded")

    def _mock_chat_auth_error(self):
        self.mock_post.return_value = MagicMock(status_code=401, text="Unauthorized")

    def _mock_chat_provider_error(self):
        self.mock_post.return_value = MagicMock(status_code=500, text="Internal server error")

    def _mock_chat_stream(self, chunks):
        mock_resp = MagicMock(status_code=200)

        async def mock_iter_lines():
            for text in chunks:
                yield f'data: {{"choices": [{{"delta": {{"content": "{text}"}}}}]}}'
            yield "data: [DONE]"

        mock_resp.aiter_lines = mock_iter_lines

        class AsyncContextMock:
            async def __aenter__(self_):
                return mock_resp
            async def __aexit__(self_, *args):
                pass

        self.mock_stream.return_value = AsyncContextMock()

    async def test_base_url(self):
        self.assertEqual(self.client.base_url, "https://api.sambanova.ai/v1")

    async def test_streaming_rate_limit_error(self):
        mock_resp = MagicMock(status_code=429)

        class AsyncContextMock:
            async def __aenter__(self_):
                return mock_resp
            async def __aexit__(self_, *args):
                pass

        self.mock_stream.return_value = AsyncContextMock()

        with self.assertRaises(RateLimitError):
            generator = await self.client.call_model_api(
                messages=[{"role": "user", "content": "Hi"}],
                model=self._model_for_test,
                stream=True,
            )
            async for _ in generator:
                pass
