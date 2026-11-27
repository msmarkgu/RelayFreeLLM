import asyncio
import json
import httpx
from typing import AsyncGenerator

from ..config import settings
from ..exceptions import ProviderError, RateLimitError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface
from .tool_support import (
    ToolResponse,
    serialize_tools,
    tool_call_deltas,
    tool_calls_from_message,
)


class OllamaClient(ApiInterface):
    """
    Client for local Ollama instances.
    Uses Ollama's OpenAI-compatible API surface.
    """

    PROVIDER_NAME = "Ollama"
    supports_tools = True

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        """Fetch local models from Ollama's tags endpoint."""
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            self.logger.error(f"Error listing Ollama models: {e}")
            return []

    async def call_model_api(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> str | AsyncGenerator[str, None]:
        """
        Call Ollama's chat completions endpoint.
        """
        url = f"{self.base_url}/v1/chat/completions"
        tool_payload = serialize_tools(tools)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tool_payload:
            payload["tools"] = tool_payload
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        try:
            if stream:
                return self._handle_stream(url, payload, bool(tool_payload))

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                message = data["choices"][0]["message"]
                if tool_payload:
                    return ToolResponse(
                        content=message.get("content") or "",
                        tool_calls=tool_calls_from_message(message),
                    )
                return message["content"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Ollama", str(e)) from e
            raise ProviderError("Ollama", f"HTTP Error {e.response.status_code}: {e}") from e
        except Exception as e:
            raise ProviderError("Ollama", str(e)) from e

    async def _handle_stream(
        self, url: str, payload: dict, with_tools: bool = False
    ) -> AsyncGenerator[str, None]:
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
                        delta = data["choices"][0]["delta"]
                        content = delta.get("content", "")
                        if content:
                            yield content
                        if with_tools and delta.get("tool_calls"):
                            yield {"tool_calls": tool_call_deltas(delta)}
                    except json.JSONDecodeError:
                        continue
