"""NVIDIA's NVCF gateway can briefly reject otherwise valid requests."""

import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import httpx

from src.api_clients.nvidia_client import NvidiaClient
from src.config import settings
from src.exceptions import ProviderError


class _AsyncContextMock:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        return None


class TestNvidiaTransientRetry(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.key_patcher = patch.object(
            settings, "get_api_key", return_value="test-key"
        )
        self.key_patcher.start()
        self.addCleanup(self.key_patcher.stop)

        self.sleep_patcher = patch.object(
            NvidiaClient, "_retry_after", new_callable=AsyncMock
        )
        self.mock_sleep = self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

        self.post_patcher = patch("httpx.AsyncClient.post", new_callable=AsyncMock)
        self.mock_post = self.post_patcher.start()
        self.addCleanup(self.post_patcher.stop)

        self.stream_patcher = patch("httpx.AsyncClient.stream")
        self.mock_stream = self.stream_patcher.start()
        self.addCleanup(self.stream_patcher.stop)

        self.client = NvidiaClient()

    async def _call(self, stream: bool = False):
        return await self.client.call_model_api(
            messages=[{"role": "user", "content": "Hi"}],
            model="nvidia/nemotron-3.5-super-vl-120b-a12b",
            stream=stream,
        )

    def _ok_response(self):
        return MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "OK"}}]},
        )

    def _rejected_response(self):
        return MagicMock(
            status_code=404,
            text="404 page not found\n",
            headers={"nvcf-error-source": "gateway_rejected"},
        )

    async def test_retries_transient_gateway_rejection(self):
        self.mock_post.side_effect = [self._rejected_response(), self._ok_response()]

        self.assertEqual(await self._call(), "OK")
        self.assertEqual(self.mock_post.await_count, 2)
        self.mock_sleep.assert_awaited_once()

    async def test_does_not_retry_real_not_found(self):
        error = MagicMock(status_code=404, text="model not found", headers={})
        self.mock_post.return_value = error

        with self.assertRaises(ProviderError):
            await self._call()
        self.assertEqual(self.mock_post.await_count, 1)
        self.mock_sleep.assert_not_awaited()

    async def test_retries_transport_error(self):
        self.mock_post.side_effect = [
            httpx.ConnectError("connection reset"),
            self._ok_response(),
        ]

        self.assertEqual(await self._call(), "OK")
        self.assertEqual(self.mock_post.await_count, 2)

    async def test_retries_transient_rejection_during_stream(self):
        async def lines():
            yield 'data: {"choices": [{"delta": {"content": "OK"}}]}'
            yield "data: [DONE]"

        ok_stream = MagicMock(status_code=200)
        ok_stream.aiter_lines = lines
        self.mock_stream.side_effect = [
            _AsyncContextMock(self._rejected_response()),
            _AsyncContextMock(ok_stream),
        ]

        chunks = []
        async for chunk in await self._call(stream=True):
            chunks.append(chunk)

        self.assertEqual(chunks, ["OK"])
        self.assertEqual(self.mock_stream.call_count, 2)


if __name__ == "__main__":
    unittest.main()
