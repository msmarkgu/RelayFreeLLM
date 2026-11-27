"""Shared client for OpenAI-compatible inference gateways.

Providers that expose ``/chat/completions`` and ``/models`` only differ in
their base URL, credentials, and a few quirks. Keeping the HTTP, SSE, and
tool-call handling here avoids four copies of the same logic; subclasses set
the provider-specific class attributes and register with the auto-discovery
registry through their ``PROVIDER_NAME``.
"""

import json

import httpx

from ..config import settings
from ..exceptions import AuthenticationError, ProviderError, RateLimitError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface
from .tool_support import (
    ToolResponse,
    serialize_tools,
    tool_call_deltas,
    tool_calls_from_message,
)


class OpenAICompatibleClient(ApiInterface):
    """Base class for gateways speaking the OpenAI Chat Completions API."""

    # Subclasses must set these. PROVIDER_NAME is deliberately left empty here
    # so ProviderRegistry.auto_discover() does not register the base class.
    KEY_NAME = ""
    BASE_URL = ""
    # Set to False for gateways that allow anonymous access to free models.
    REQUIRES_API_KEY = True
    # Tried in order; useful when a gateway has a preferred model endpoint but
    # also supports the generic OpenAI /models route.
    MODELS_PATHS = ("/models",)
    MODELS_REQUIRE_AUTH = True
    EXTRA_HEADERS: dict[str, str] = {}

    supports_tools = True
    supports_multimodal = False
    max_output_tokens_cap: int | None = None

    def __init__(self):
        self.api_key = (
            settings.get_api_key(self.KEY_NAME) if self.REQUIRES_API_KEY else ""
        )
        self.base_url = self.BASE_URL.rstrip("/")
        self.logger = ProjectLogger.get_logger(__name__)
        self.default_headers = {
            "Content-Type": "application/json",
            # Some CDNs block generic default User-Agents from HTTP clients.
            "User-Agent": "RelayFreeLLM/1.0 (https://github.com/msmarkgu/RelayFreeLLM)",
        }
        if self.api_key:
            self.default_headers["Authorization"] = f"Bearer {self.api_key}"
        self.default_headers.update(self.EXTRA_HEADERS)

    def _headers(self, authenticated: bool = True) -> dict[str, str]:
        headers = dict(self.default_headers)
        if not authenticated or not self.api_key:
            headers.pop("Authorization", None)
        return headers

    def _raise_for_status(self, response) -> None:
        status = response.status_code
        if status in (402, 429):
            # Requesty 402 means the organization balance is exhausted; map it
            # to a rate limit so the dispatcher fails over and applies cooldown.
            raise RateLimitError(self.PROVIDER_NAME, f"Rate limited: {response.text}")
        if status in (401, 403):
            raise AuthenticationError(self.PROVIDER_NAME, f"Auth failed: {response.text}")
        if status != 200:
            raise ProviderError(
                self.PROVIDER_NAME,
                f"API Error {status}: {response.text}",
            )

    async def list_models(self) -> list[str]:
        for path in self.MODELS_PATHS:
            try:
                async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
                    response = await client.get(
                        f"{self.base_url}{path}",
                        headers=self._headers(self.MODELS_REQUIRE_AUTH),
                    )
                if response.status_code == 200:
                    data = response.json()
                    models = [
                        entry["id"]
                        for entry in data.get("data", [])
                        if isinstance(entry, dict) and entry.get("id")
                    ]
                    if models:
                        return models
                    self.logger.warning(
                        f"{self.PROVIDER_NAME} returned no models from {path}."
                    )
                else:
                    self.logger.warning(
                        f"{self.PROVIDER_NAME} list models error from {path}: "
                        f"{response.status_code} - {response.text}"
                    )
            except Exception as e:
                self.logger.error(
                    f"{self.PROVIDER_NAME} list models request failed for {path}: {e}"
                )
        return []

    async def call_model_api(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.8,
        max_tokens: int = 4000,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> str | object:
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

        if stream:
            return self._stream_response(payload, bool(tool_payload))

        try:
            async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            self._raise_for_status(response)

            message = response.json()["choices"][0]["message"]
            content = message.get("content")
            if not content:
                content = message.get("reasoning_content") or message.get("reasoning") or ""
            if tool_payload:
                return ToolResponse(
                    content=content or "",
                    tool_calls=tool_calls_from_message(message),
                )
            return content or ""
        except (RateLimitError, AuthenticationError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.PROVIDER_NAME, str(e)) from e

    async def _stream_response(self, payload: dict, with_tools: bool = False):
        client = httpx.AsyncClient(timeout=settings.HTTP_STREAM_TIMEOUT)
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                self._raise_for_status(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk["choices"]
                        delta = choices[0]["delta"]
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        # Gateways may interleave non-chunk events (routing,
                        # usage, comments) into the same SSE stream.
                        continue
                    content = delta.get("content")
                    if not content:
                        content = (
                            delta.get("reasoning_content")
                            or delta.get("reasoning")
                            or ""
                        )
                    if content:
                        yield content
                    if with_tools and delta.get("tool_calls"):
                        yield {"tool_calls": tool_call_deltas(delta)}
        finally:
            await client.aclose()
