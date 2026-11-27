import asyncio
import base64
import re
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
    supports_multimodal = True

    def __init__(self):
        api_key = settings.get_api_key("GEMINI_APIKEY")
        # Note: http_options.timeout doesn't apply to all SDK internal calls
        # Keep original client config without custom timeout
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

    @staticmethod
    def _content_to_gemini_parts(content: str | list) -> list:
        """Convert a content field (string or OpenAI-format parts list)
        to a list of Gemini Part objects."""
        parts = []
        if isinstance(content, str):
            parts.append(types.Part.from_text(text=content))
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype == "text":
                    parts.append(types.Part.from_text(text=part.get("text", "")))
                elif ptype == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url.startswith("data:image/"):
                        match = re.match(r"data:image/(\w+);base64,(.+)", url)
                        if match:
                            mime = f"image/{match.group(1)}"
                            data = base64.b64decode(match.group(2))
                            parts.append(types.Part.from_bytes(data=data, mime_type=mime))
                    elif url:
                        parts.append(types.Part.from_uri(uri=url, mime_type="image/jpeg"))
        return parts

    async def call_model_api(
        self,
        messages: list[dict],
        model: str = "gemini-2.5-pro",
        temperature: float = 0.8,
        max_tokens: int = 4000,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> str | object:

        try:
            sys_instruct = ""
            gemini_contents = []
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                sys_instruct += part.get("text", "") + "\n"
                    else:
                        sys_instruct += content + "\n"
                else:
                    gemini_role = "model" if role == "assistant" else role
                    parts = self._content_to_gemini_parts(content)
                    if parts:
                        gemini_contents.append(
                            types.Content(role=gemini_role, parts=parts)
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
            text = response.text
            return text if text is not None else ""

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str or "quota" in error_str or "resource_exhausted" in error_str:
                raise RateLimitError("Gemini", str(e)) from e
            if "401" in error_str or "403" in error_str or "api key" in error_str:
                raise AuthenticationError("Gemini", str(e)) from e
            raise ProviderError("Gemini", str(e)) from e
