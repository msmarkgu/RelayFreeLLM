import asyncio
import traceback

from groq import Groq

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface


class GroqClient(ApiInterface):

    PROVIDER_NAME = "Groq"

    def __init__(self):
        api_key = settings.get_api_key("GROQ_APIKEY")
        self.client = Groq(api_key=api_key, timeout=settings.REQUEST_TIMEOUT_SECONDS)
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        try:
            models = self.client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            self.logger.error(f"Error listing Groq models: {e}")
            return []

    async def call_model_api(
        self,
        messages: list[dict],
        model: str = "qwen/qwen3-32b",
        temperature: float = 0.8,
        max_tokens: int = 4000,
        stream: bool = False,
    ) -> str | object:

        try:
            if stream:

                async def generate():
                    stream_resp = self.client.chat.completions.create(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_completion_tokens=max_tokens,
                        stream=True,
                    )
                    for chunk in stream_resp:
                        if chunk.choices and chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content

                return generate()

            chat_completion = self.client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=temperature,
                max_completion_tokens=max_tokens,
                top_p=1,
                stop=None,
                stream=False,
            )

            if (
                chat_completion
                and chat_completion.choices
                and len(chat_completion.choices) > 0
            ):
                return chat_completion.choices[0].message.content
            else:
                raise ProviderError("Groq", "No response from the model.")

        except ProviderError:
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise RateLimitError("Groq", str(e)) from e
            if "401" in error_str or "api key" in error_str:
                raise AuthenticationError("Groq", str(e)) from e
            raise ProviderError("Groq", str(e)) from e
