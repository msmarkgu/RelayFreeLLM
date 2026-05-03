import asyncio
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.api_clients.nvidia_client import NvidiaClient
from src.exceptions import ProviderError, RateLimitError, AuthenticationError


class TestNvidiaClient(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        with patch.dict(os.environ, {"NVIDIA_APIKEY": "test-api-key"}):
            self.client = NvidiaClient()

    @patch("httpx.AsyncClient.get")
    async def test_list_models_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "meta/llama-3.1-70b-instruct"},
                {"id": "meta/llama-3.3-70b-instruct"},
                {"id": "nvidia/llama-3.1-nemotron-70b-instruct"}
            ]
        }
        mock_get.return_value = mock_response

        models = await self.client.list_models()
        self.assertEqual(len(models), 3)
        self.assertIn("meta/llama-3.1-70b-instruct", models)
        self.assertIn("meta/llama-3.3-70b-instruct", models)

    @patch("httpx.AsyncClient.get")
    async def test_list_models_empty(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        models = await self.client.list_models()
        self.assertEqual(len(models), 0)

    @patch("httpx.AsyncClient.get")
    async def test_list_models_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        models = await self.client.list_models()
        self.assertEqual(len(models), 0)

    @patch("httpx.AsyncClient.post")
    async def test_call_model_api_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "Hello from NVIDIA NIM"}}
            ]
        }
        mock_post.return_value = mock_response

        response = await self.client.call_model_api(
            messages=[
                {"role": "system", "content": "Be helpful"},
                {"role": "user", "content": "Hi"}
            ],
            model="meta/llama-3.1-70b-instruct",
            temperature=0.7,
            max_tokens=100
        )
        self.assertEqual(response, "Hello from NVIDIA NIM")

    @patch("httpx.AsyncClient.post")
    async def test_call_model_api_rate_limit(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_post.return_value = mock_response

        with self.assertRaises(RateLimitError) as context:
            await self.client.call_model_api(
                messages=[{"role": "user", "content": "Hi"}],
                model="meta/llama-3.1-70b-instruct"
            )
        self.assertEqual(context.exception.provider, "Nvidia")

    @patch("httpx.AsyncClient.post")
    async def test_call_model_api_auth_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        with self.assertRaises(AuthenticationError) as context:
            await self.client.call_model_api(
                messages=[{"role": "user", "content": "Hi"}],
                model="meta/llama-3.1-70b-instruct"
            )
        self.assertEqual(context.exception.provider, "Nvidia")

    @patch("httpx.AsyncClient.post")
    async def test_call_model_api_provider_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_post.return_value = mock_response

        with self.assertRaises(ProviderError) as context:
            await self.client.call_model_api(
                messages=[{"role": "user", "content": "Hi"}],
                model="meta/llama-3.1-70b-instruct"
            )
        self.assertEqual(context.exception.provider, "Nvidia")

    @patch("httpx.AsyncClient.stream")
    async def test_call_model_api_streaming(self, mock_stream):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        async def mock_iter_lines():
            yield 'data: {"choices": [{"delta": {"content": "Hello"}}]}'
            yield 'data: {"choices": [{"delta": {"content": " from"}}]}'
            yield 'data: {"choices": [{"delta": {"content": " NVIDIA"}}]}'
            yield 'data: [DONE]'

        mock_resp.aiter_lines = mock_iter_lines

        class AsyncContextMock:
            async def __aenter__(self):
                return mock_resp
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_stream.return_value = AsyncContextMock()

        generator = await self.client.call_model_api(
            messages=[
                {"role": "system", "content": "Be helpful"},
                {"role": "user", "content": "Hi"}
            ],
            model="meta/llama-3.1-70b-instruct",
            temperature=0.7,
            max_tokens=100,
            stream=True
        )

        chunks = []
        async for chunk in generator:
            chunks.append(chunk)

        self.assertEqual("".join(chunks), "Hello from NVIDIA")

    @patch("httpx.AsyncClient.stream")
    async def test_streaming_rate_limit_error(self, mock_stream):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        class AsyncContextMock:
            async def __aenter__(self):
                return mock_resp
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_stream.return_value = AsyncContextMock()

        with self.assertRaises(RateLimitError):
            generator = await self.client.call_model_api(
                messages=[{"role": "user", "content": "Hi"}],
                model="meta/llama-3.1-70b-instruct",
                stream=True
            )
            async for _ in generator:
                pass

    def test_provider_name(self):
        self.assertEqual(self.client.PROVIDER_NAME, "Nvidia")

    def test_base_url(self):
        self.assertEqual(self.client.base_url, "https://integrate.api.nvidia.com/v1")


class TestNvidiaModelsConfiguration(unittest.TestCase):

    def test_nvidia_models_in_config(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'provider_model_limits.json')
        with open(config_path, 'r') as f:
            config = json.load(f)

        nvidia_provider = None
        for provider in config['providers']:
            if provider['name'] == 'Nvidia':
                nvidia_provider = provider
                break

        self.assertIsNotNone(nvidia_provider, "Nvidia provider not found in config")
        self.assertGreater(len(nvidia_provider['models']), 0, "No models configured for Nvidia")

        for model in nvidia_provider['models']:
            self.assertIn('name', model, f"Model missing 'name' field")
            self.assertIsInstance(model['name'], str, f"Model name should be string")
            self.assertGreater(len(model['name']), 0, f"Model name should not be empty")

    def test_nvidia_models_no_small_scale(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'provider_model_limits.json')
        with open(config_path, 'r') as f:
            config = json.load(f)

        nvidia_provider = None
        for provider in config['providers']:
            if provider['name'] == 'Nvidia':
                nvidia_provider = provider
                break

        for model in nvidia_provider['models']:
            self.assertNotEqual(model['scale'], 'small',
                f"Model {model['name']} has 'small' scale, should only have large models")

    def test_nvidia_models_have_context_length(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'provider_model_limits.json')
        with open(config_path, 'r') as f:
            config = json.load(f)

        nvidia_provider = None
        for provider in config['providers']:
            if provider['name'] == 'Nvidia':
                nvidia_provider = provider
                break

        for model in nvidia_provider['models']:
            self.assertIn('Max_Context_Length', model,
                f"Model {model['name']} missing Max_Context_Length")
            self.assertGreater(model['Max_Context_Length'], 0,
                f"Model {model['name']} has invalid Max_Context_Length")


if __name__ == "__main__":
    unittest.main()
