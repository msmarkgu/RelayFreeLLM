import asyncio
import traceback

from mistralai.client import Mistral

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface


class MistralClient(ApiInterface):

    PROVIDER_NAME = "Mistral"

    def __init__(self):
        api_key = settings.get_api_key("MISTRAL_APIKEY")
        self.client = Mistral(api_key=api_key)
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        try:
            models = self.client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            self.logger.error(f"Error listing Mistral models: {e}")
            return []

    async def call_model_api(
        self,
        messages: list[dict],
        model: str = "mistral-small-2507",
        temperature: float = 0.8,
        max_tokens: int = 4000,
        stream: bool = False,
    ) -> str | object:
        await asyncio.sleep(1)

        try:
            if stream:

                async def generate():
                    async_stream = await self.client.chat.stream_async(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    async for chunk in async_stream:
                        content = chunk.data.choices[0].delta.content
                        if content:
                            yield content

                return generate()

            chat_response = self.client.chat.complete(
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=1,
                max_tokens=max_tokens,
            )
            content = chat_response.choices[0].message.content

            # Handle structured content from reasoning models (e.g. magistral)
            # which return ThinkChunk/TextChunk objects instead of plain strings
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                # Extract text from chunk objects
                parts = []
                for chunk in content:
                    if hasattr(chunk, "text"):
                        parts.append(chunk.text)
                    elif isinstance(chunk, str):
                        parts.append(chunk)
                return "\n".join(parts) if parts else str(content)
            else:
                return str(content)

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise RateLimitError("Mistral", str(e)) from e
            if "401" in error_str or "api key" in error_str:
                raise AuthenticationError("Mistral", str(e)) from e
            raise ProviderError("Mistral", str(e)) from e
