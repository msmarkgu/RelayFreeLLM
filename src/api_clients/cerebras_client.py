import asyncio
import traceback

from cerebras.cloud.sdk import Cerebras

from ..config import settings
from ..exceptions import ProviderError, RateLimitError, AuthenticationError
from ..logging_util import ProjectLogger
from .api_interface import ApiInterface
from .tool_support import (
    ToolResponse,
    serialize_tools,
    tool_call_deltas,
    tool_calls_from_message,
)


class CerebrasClient(ApiInterface):

    PROVIDER_NAME = "Cerebras"
    supports_tools = True

    def __init__(self):
        api_key = settings.get_api_key("CEREBRAS_APIKEY")
        self.client = Cerebras(api_key=api_key, timeout=settings.REQUEST_TIMEOUT_SECONDS)
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
        messages: list[dict],
        model: str = "gpt-oss-120b",
        temperature: float = 0.8,
        max_tokens: int = 4000,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> str | object:

        try:
            tool_payload = serialize_tools(tools)
            extra = {}
            if tool_payload:
                extra["tools"] = tool_payload
                if tool_choice is not None:
                    extra["tool_choice"] = tool_choice

            if stream:

                async def generate():
                    stream_resp = self.client.chat.completions.create(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_completion_tokens=max_tokens,
                        stream=True,
                        **extra,
                    )
                    for chunk in stream_resp:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield delta.content
                        deltas = tool_call_deltas(delta)
                        if deltas:
                            yield {"tool_calls": deltas}

                return generate()

            chat_completion = self.client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.5,
                max_completion_tokens=max_tokens,
                top_p=1,
                stop=None,
                stream=False,
                **extra,
            )

            if (
                chat_completion
                and chat_completion.choices
                and len(chat_completion.choices) > 0
            ):
                message = chat_completion.choices[0].message
                if tool_payload:
                    return ToolResponse(
                        content=message.content or "",
                        tool_calls=tool_calls_from_message(message),
                    )
                return message.content if message.content is not None else ""
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
