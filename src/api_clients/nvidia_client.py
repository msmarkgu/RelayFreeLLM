import asyncio
import httpx
import json

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface
from .tool_support import (
    ToolResponse,
    serialize_tools,
    tool_call_deltas,
    tool_calls_from_message,
)


class NvidiaClient(ApiInterface):

    PROVIDER_NAME = "Nvidia"
    supports_tools = True

    # NVIDIA's NVCF gateway occasionally answers a valid model request with
    # "404 page not found" (nvcf-error-source: gateway_rejected) or drops the
    # connection. Retry those transient failures instead of surfacing a 502
    # to Claude Code on the first blip.
    TRANSIENT_ATTEMPTS = 3
    RETRY_BASE_DELAY = 0.4

    def __init__(self):
        self.api_key = settings.get_api_key("NVIDIA_APIKEY")
        self.base_url = "https://integrate.api.nvidia.com/v1"
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        if not self.api_key:
            self.logger.warning("NVIDIA API key missing. Skipping model listing.")
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        try:
            async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=headers
                )
                if response.status_code == 200:
                    data = response.json()
                    return [m["id"] for m in data.get("data", [])]
                else:
                    self.logger.error(f"NVIDIA List Models API Error: {response.status_code} - {response.text}")
                    return []
        except Exception as e:
            self.logger.error(f"NVIDIA List Models Connection Error: {e}")
            return []

    @classmethod
    def _is_transient_response(cls, response) -> bool:
        """NVIDIA NVCF gateway rejections that are safe to retry."""
        headers = getattr(response, "headers", None) or {}
        if headers.get("nvcf-error-source") == "gateway_rejected":
            return True
        body = getattr(response, "text", "") or ""
        return response.status_code == 404 and "404 page not found" in body.lower()

    @classmethod
    async def _retry_after(cls, attempt: int) -> None:
        await asyncio.sleep(cls.RETRY_BASE_DELAY * (2**attempt))

    async def call_model_api(
        self,
        messages: list[dict],
        model: str = "meta/llama-3.1-8b-instruct",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> str | object:

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        tool_payload = serialize_tools(tools)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        if tool_payload:
            payload["tools"] = tool_payload
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        try:
            if stream:
                return self._stream_response(payload, headers, bool(tool_payload))

            async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
                for attempt in range(self.TRANSIENT_ATTEMPTS):
                    try:
                        response = await client.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=payload
                        )
                    except httpx.TransportError as exc:
                        if attempt + 1 < self.TRANSIENT_ATTEMPTS:
                            self.logger.warning(
                                f"NVIDIA connection error, retrying "
                                f"({attempt + 1}/{self.TRANSIENT_ATTEMPTS}): {exc}"
                            )
                            await self._retry_after(attempt)
                            continue
                        raise ProviderError("Nvidia", f"Connection error: {exc}") from exc

                    if (
                        attempt + 1 < self.TRANSIENT_ATTEMPTS
                        and self._is_transient_response(response)
                    ):
                        self.logger.warning(
                            f"NVIDIA transient gateway rejection, retrying "
                            f"({attempt + 1}/{self.TRANSIENT_ATTEMPTS}): "
                            f"HTTP {response.status_code}"
                        )
                        await self._retry_after(attempt)
                        continue
                    break

                if response.status_code == 200:
                    data = response.json()
                    message = data["choices"][0]["message"]
                    content = message.get("content")
                    if content is None:
                        content = message.get("reasoning", "")
                    if tool_payload:
                        return ToolResponse(
                            content=content or "",
                            tool_calls=tool_calls_from_message(message),
                        )
                    return content
                elif response.status_code == 429:
                    raise RateLimitError("Nvidia", f"Rate limited: {response.text}")
                elif response.status_code in (401, 403):
                    raise AuthenticationError("Nvidia", f"Auth failed: {response.text}")
                else:
                    raise ProviderError("Nvidia", f"API Error {response.status_code}: {response.text}")

        except (RateLimitError, AuthenticationError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError("Nvidia", str(e)) from e

    async def _consume_stream(self, response, with_tools: bool):
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
                if not content:
                    content = delta.get("reasoning", "")
                if content:
                    yield content
                if with_tools and delta.get("tool_calls"):
                    yield {"tool_calls": tool_call_deltas(delta)}
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

    async def _stream_response(
        self, payload: dict, headers: dict, with_tools: bool = False
    ):
        client = httpx.AsyncClient(timeout=settings.HTTP_STREAM_TIMEOUT)
        try:
            for attempt in range(self.TRANSIENT_ATTEMPTS):
                retry = False
                stream_started = False
                try:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        if response.status_code == 429:
                            raise RateLimitError("Nvidia", "Rate limited during streaming")
                        if response.status_code in (401, 403):
                            raise AuthenticationError("Nvidia", "Auth failed during streaming")
                        if response.status_code == 200:
                            stream_started = True
                            async for item in self._consume_stream(response, with_tools):
                                yield item
                            return

                        if (
                            attempt + 1 < self.TRANSIENT_ATTEMPTS
                            and self._is_transient_response(response)
                        ):
                            retry = True
                        else:
                            body = await response.aread()
                            raise ProviderError(
                                "Nvidia",
                                f"API Error {response.status_code}: "
                                f"{body.decode(errors='replace')}",
                            )
                except httpx.TransportError as exc:
                    # A drop after content started would duplicate output on retry.
                    if stream_started or attempt + 1 >= self.TRANSIENT_ATTEMPTS:
                        raise ProviderError("Nvidia", f"Connection error: {exc}") from exc
                    retry = True

                if retry:
                    self.logger.warning(
                        f"NVIDIA transient streaming failure, retrying "
                        f"({attempt + 1}/{self.TRANSIENT_ATTEMPTS})"
                    )
                    await self._retry_after(attempt)
        finally:
            await client.aclose()
