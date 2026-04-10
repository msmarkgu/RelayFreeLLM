import asyncio
import httpx
import traceback

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface


class DeepSeekClient(ApiInterface):

    PROVIDER_NAME = "DeepSeek"

    def __init__(self):
        self.api_key = settings.get_api_key("DEEPSEEK_APIKEY")
        self.base_url = "https://api.deepseek.com/v1"
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        if not self.api_key:
            self.logger.warning("DeepSeek API key missing. Skipping model listing.")
            return []
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=headers
                )
                if response.status_code == 200:
                    data = response.json()
                    return [m["id"] for m in data.get("data", [])]
                else:
                    self.logger.error(f"DeepSeek List Models API Error: {response.status_code} - {response.text}")
                    return []
        except Exception as e:
            self.logger.error(f"DeepSeek List Models Connection Error: {e}")
            return []

    async def call_model_api(self, 
                             messages: list[dict],
                             model="deepseek-chat", 
                             temperature=0.7, 
                             max_tokens=4000) -> str:
        await asyncio.sleep(0.5)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                elif response.status_code == 429:
                    raise RateLimitError("DeepSeek", f"Rate limited: {response.text}")
                elif response.status_code in (401, 403):
                    raise AuthenticationError("DeepSeek", f"Auth failed: {response.text}")
                else:
                    raise ProviderError("DeepSeek", f"API Error {response.status_code}: {response.text}")

        except (RateLimitError, AuthenticationError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError("DeepSeek", str(e)) from e
