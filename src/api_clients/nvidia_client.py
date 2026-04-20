import httpx
import json

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface


class NvidiaClient(ApiInterface):

    PROVIDER_NAME = "Nvidia"

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

    async def call_model_api(
        self,
        messages: list[dict],
        model: str = "meta/llama-3.1-8b-instruct",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        stream: bool = False,
    ) -> str | object:

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }

        try:
            async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
                if stream:
                    return self._stream_response(client, payload, headers)

                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )

                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
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

    async def _stream_response(self, client: httpx.AsyncClient, payload: dict, headers: dict):
        async with client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=settings.HTTP_STREAM_TIMEOUT
        ) as response:
            if response.status_code == 429:
                raise RateLimitError("Nvidia", "Rate limited during streaming")
            if response.status_code in (401, 403):
                raise AuthenticationError("Nvidia", "Auth failed during streaming")
            if response.status_code != 200:
                raise ProviderError("Nvidia", f"API Error {response.status_code}")

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
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
