import asyncio
import traceback

from google import genai
from google.genai import types

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .client_config import ClientConfig
from .api_interface import ApiInterface


class GeminiClient(ApiInterface):

    PROVIDER_NAME = "Gemini"

    def __init__(self):
        api_key = settings.get_api_key("GEMINI_APIKEY")
        self.client = genai.Client(api_key=api_key)
        self.logger = ProjectLogger.get_logger(__name__)

    async def list_models(self) -> list[str]:
        try:
            models = self.client.models.list()
            chat_models = [m.name for m in models if 'generateContent' in m.supported_actions]
            return [m.replace('models/', '') for m in chat_models]
        except Exception as e:
            self.logger.error(f"Error listing Gemini models: {e}")
            return []

    async def call_model_api(self, 
                             user_prompt="introduce yourself", 
                             model="gemini-2.5-pro", 
                             sys_instruct="return answer in markdown", 
                             temperature=0.8, 
                             max_tokens=4000) -> str:
        await asyncio.sleep(1)

        try:
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruct,
                    max_output_tokens=max_tokens,
                    top_k=1,
                    top_p=0.8,
                    temperature=temperature,
                    seed=42,
                    safety_settings=ClientConfig.GEMINI_SAFETY_SETTINGS,
                    tools=[
                        types.Tool(
                            google_search=types.GoogleSearch()
                        )
                    ]
                )
            )
            return response.text

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str or "quota" in error_str or "resource_exhausted" in error_str:
                raise RateLimitError("Gemini", str(e)) from e
            if "401" in error_str or "403" in error_str or "api key" in error_str:
                raise AuthenticationError("Gemini", str(e)) from e
            raise ProviderError("Gemini", str(e)) from e
