import asyncio
import json
import httpx
from typing import AsyncGenerator

from ..config import settings
from ..exceptions import ProviderError, RateLimitError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface


class OllamaClient(ApiInterface):
    """
    Client for local Ollama instances.
    Uses Ollama's OpenAI-compatible API surface.
    """

    PROVIDER_NAME = "Ollama"

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        """Fetch local models from Ollama's tags endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            self.logger.error(f"Error listing Ollama models: {e}")
            return []

    async def call_model_api(
        self,
        user_prompt: str,
        model: str,
        sys_instruct: str,
        temperature: float,
        max_tokens: int,
        stream: bool = False,
    ) -> str | AsyncGenerator[str, None]:
        """
        Call Ollama's chat completions endpoint.
        """
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_instruct},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        try:
            if stream:
                return self._handle_stream(url, payload)

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Ollama", str(e)) from e
            raise ProviderError("Ollama", f"HTTP Error {e.response.status_code}: {e}") from e
        except Exception as e:
            raise ProviderError("Ollama", str(e)) from e

    async def _handle_stream(self, url: str, payload: dict) -> AsyncGenerator[str, None]:
        """Generator for Ollama's streaming responses."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    data_str = line[len("data: "):]
                    if data_str == "[DONE]":
                        break
                        
                    try:
                        data = json.loads(data_str)
                        content = data["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
