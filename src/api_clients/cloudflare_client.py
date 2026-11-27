import asyncio
import httpx
import traceback

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface
from .tool_support import ToolResponse, serialize_tools, tool_calls_from_message


class CloudflareClient(ApiInterface):

    PROVIDER_NAME = "Cloudflare"
    supports_tools = True

    def __init__(self):
        try:
            self.api_token = settings.get_api_key("CLOUDFLARE_API_TOKEN")
            self.account_id = settings.get_api_key("CLOUDFLARE_ACCOUNT_ID")
        except ValueError:
            self.api_token = None
            self.account_id = None
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        if not self.api_token or not self.account_id:
            self.logger.warning("Cloudflare credentials missing. Skipping model listing.")
            return []

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/models/search?task=text-generation"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                if data.get("success"):
                    return [m["name"] for m in data.get("result", [])]
                else:
                    self.logger.error(f"Cloudflare API error: {data.get('errors')}")
                    return []
        except Exception as e:
            self.logger.error(f"Error listing Cloudflare models: {e}")
            return []

    async def call_model_api(self, 
                             messages: list[dict], 
                             model="@cf/meta/llama-3.1-8b-instruct", 
                             temperature=0.8, 
                             max_tokens=2048,
                             stream: bool = False,
                             tools: list[dict] | None = None,
                             tool_choice: str | dict | None = None) -> str:
        if stream:
            raise ProviderError("Cloudflare", "Streaming is not supported by this client.")
        if not self.api_token or not self.account_id:
            raise AuthenticationError("Cloudflare", "Cloudflare credentials missing.")

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        tool_payload = serialize_tools(tools)
        payload = {
            "messages": messages,

            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if tool_payload:
            payload["tools"] = tool_payload
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                await asyncio.sleep(0.5)
                
                response = await client.post(url, headers=headers, json=payload, timeout=60.0)
                
                if response.status_code == 200:
                    data = response.json()
                    message = data["choices"][0]["message"]
                    if tool_payload:
                        return ToolResponse(
                            content=message.get("content") or "",
                            tool_calls=tool_calls_from_message(message),
                        )
                    return message["content"]
                elif response.status_code == 429:
                    raise RateLimitError("Cloudflare", f"Rate limited: {response.text}")
                elif response.status_code in (401, 403):
                    raise AuthenticationError("Cloudflare", f"Auth failed: {response.text}")
                else:
                    raise ProviderError("Cloudflare", f"API Error {response.status_code}: {response.text}")

        except (RateLimitError, AuthenticationError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError("Cloudflare", str(e)) from e
