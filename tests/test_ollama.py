import asyncio
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import json
import httpx

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.api_clients.ollama_client import OllamaClient
from src.exceptions import ProviderError, RateLimitError

class TestOllamaClient(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.client = OllamaClient()

    @patch("httpx.AsyncClient.get")
    async def test_list_models(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:latest"},
                {"name": "mistral:latest"}
            ]
        }
        mock_get.return_value = mock_response

        models = await self.client.list_models()
        self.assertEqual(len(models), 2)
        self.assertIn("llama3:latest", models)

    @patch("httpx.AsyncClient.post")
    async def test_call_model_api_non_streaming(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "Hello from Ollama"}}
            ]
        }
        mock_post.return_value = mock_response

        response = await self.client.call_model_api(
            user_prompt="Hi",
            model="llama3",
            sys_instruct="Be helpful",
            temperature=0.7,
            max_tokens=100
        )
        self.assertEqual(response, "Hello from Ollama")

    @patch("httpx.AsyncClient.stream")
    async def test_call_model_api_streaming(self, mock_stream):
        # Mocking async context manager for httpx.stream
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        
        async def mock_iter_lines():
            yield 'data: {"choices": [{"delta": {"content": "Hello"}}]}'
            yield 'data: {"choices": [{"delta": {"content": " World"}}]}'
            yield 'data: [DONE]'
            
        mock_resp.aiter_lines = mock_iter_lines
        
        # Setup mock_stream to return an async context manager
        class AsyncContextMock:
            async def __aenter__(self):
                return mock_resp
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_stream.return_value = AsyncContextMock()

        generator = await self.client.call_model_api(
            user_prompt="Hi",
            model="llama3",
            sys_instruct="Be helpful",
            temperature=0.7,
            max_tokens=100,
            stream=True
        )
        
        chunks = []
        async for chunk in generator:
            chunks.append(chunk)
            
        self.assertEqual("".join(chunks), "Hello World")

if __name__ == "__main__":
    unittest.main()
