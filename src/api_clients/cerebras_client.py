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

    async def call_model_api(self, 
                             user_prompt="introduce yourself", 
                             model="gpt-oss-120b", 
                             sys_instruct="return answer in markdown", 
                             temperature=0.8, 
                             max_tokens=4000) -> str:
        await asyncio.sleep(1)

        try:
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

            if chat_completion and chat_completion.choices and len(chat_completion.choices) > 0:
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
