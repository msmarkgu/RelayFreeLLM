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

    async def call_model_api(
        self,
        messages: list[dict],
        model: str = "gemini-2.5-pro",
        temperature: float = 0.8,
        max_tokens: int = 4000,
        stream: bool = False,
    ) -> str | object:

        try:
            sys_instruct = ""
            gemini_contents = []
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    sys_instruct += content + "\n"
                else:
                    gemini_role = "model" if role == "assistant" else role
                    gemini_contents.append(
                        types.Content(
                            role=gemini_role,
                            parts=[types.Part.from_text(text=content)]
                        )
                    )
                    
            config = types.GenerateContentConfig(
                system_instruction=sys_instruct.strip() if sys_instruct else None,
                max_output_tokens=max_tokens,
                top_k=1,
                top_p=0.8,
                temperature=temperature,
                seed=42,
                safety_settings=ClientConfig.GEMINI_SAFETY_SETTINGS,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )

            if stream:

                async def generate():
                    async for response in await self.client.aio.models.generate_content_stream(
                        model=model, contents=gemini_contents, config=config
                    ):
                        if response.text:
                            yield response.text

                return generate()

            response = await self.client.aio.models.generate_content(
                model=model, contents=gemini_contents, config=config
            )
            return response.text

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str or "quota" in error_str or "resource_exhausted" in error_str:
                raise RateLimitError("Gemini", str(e)) from e
            if "401" in error_str or "403" in error_str or "api key" in error_str:
                raise AuthenticationError("Gemini", str(e)) from e
            raise ProviderError("Gemini", str(e)) from e
