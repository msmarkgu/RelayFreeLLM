import json

import httpx

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface


class SambaNovaClient(ApiInterface):

    PROVIDER_NAME = "SambaNova"
    supports_multimodal = True

    BASE_URL = "https://api.sambanova.ai/v1"

    def __init__(self):
        self.api_key = settings.get_api_key("SAMBANOVA_APIKEY")
        self.base_url = self.BASE_URL
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        if not self.api_key:
            self.logger.warning("SambaNova API key missing. Skipping model listing.")
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/models", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return [m["id"] for m in data.get("data", [])]
                else:
                    self.logger.error(
                        f"SambaNova List Models API Error: {response.status_code} - {response.text}"
                    )
                    return []
        except Exception as e:
            self.logger.error(f"SambaNova List Models Connection Error: {e}")
            return []

    async def call_model_api(
        self,
        messages: list[dict],
        model: str = "Meta-Llama-3.3-70B-Instruct",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        stream: bool = False,
    ) -> str | object:

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        try:
            if stream:
                return self._stream_response(payload, headers)

            async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"].get("content")
                    if content is None:
                        content = ""
                    return content
                elif response.status_code == 429:
                    raise RateLimitError("SambaNova", f"Rate limited: {response.text}")
                elif response.status_code in (401, 403):
                    raise AuthenticationError("SambaNova", f"Auth failed: {response.text}")
                else:
                    raise ProviderError("SambaNova", f"API Error {response.status_code}: {response.text}")

        except (RateLimitError, AuthenticationError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError("SambaNova", str(e)) from e

    async def _stream_response(self, payload: dict, headers: dict):
        client = httpx.AsyncClient(timeout=settings.HTTP_STREAM_TIMEOUT)
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code == 429:
                    raise RateLimitError("SambaNova", "Rate limited during streaming")
                if response.status_code in (401, 403):
                    raise AuthenticationError("SambaNova", "Auth failed during streaming")
                if response.status_code != 200:
                    body = await response.aread()
                    raise ProviderError(
                        "SambaNova",
                        f"API Error {response.status_code}: {body.decode(errors='replace')}",
                    )

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
        finally:
            await client.aclose()
