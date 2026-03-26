import asyncio
import traceback

from cerebras.cloud.sdk import Cerebras

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface


class CerebrasClient(ApiInterface):

    PROVIDER_NAME = "Cerebras"

    def __init__(self):
        api_key = settings.get_api_key("CEREBRAS_APIKEY")
        self.client = Cerebras(api_key=api_key)
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        try:
            models = self.client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            self.logger.error(f"Error listing Cerebras models: {e}")
            return []

    async def call_model_api(
        self,
        user_prompt: str = "introduce yourself",
        model: str = "gpt-oss-120b",
        sys_instruct: str = "return answer in markdown",
        temperature: float = 0.8,
        max_tokens: int = 4000,
        stream: bool = False,
    ) -> str | object:
        await asyncio.sleep(1)

        try:
            if stream:

                async def generate():
                    stream_resp = self.client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": sys_instruct},
                            {"role": "user", "content": user_prompt},
                        ],
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
                messages=[
                    {"role": "system", "content": sys_instruct},
                    {"role": "user", "content": user_prompt},
                ],
                model=model,
                temperature=0.5,
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
                raise ProviderError("Cerebras", "No response from the model.")

        except ProviderError:
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise RateLimitError("Cerebras", str(e)) from e
            if "401" in error_str or "api key" in error_str:
                raise AuthenticationError("Cerebras", str(e)) from e
            raise ProviderError("Cerebras", str(e)) from e
