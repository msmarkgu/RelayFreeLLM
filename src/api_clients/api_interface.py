"""
Abstract interface for all AI provider clients.

Each provider client must implement:
  - call_model_api(): Send a prompt and get a response
  - list_models(): Discover available models on the provider
"""

from abc import ABC, abstractmethod

from ..config import settings


class ApiInterface(ABC):

    PROVIDER_NAME: str = ""
    supports_multimodal: bool = False
    # Set to True by clients that can forward tool definitions and surface
    # tool calls in their responses.
    supports_tools: bool = False

    @abstractmethod
    async def call_model_api(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> str | object:
        pass

    @abstractmethod
    async def list_models(self) -> list[str]:
        pass

    @staticmethod
    def load_api_key(key_name: str) -> str:
        """Load an API key from environment variables via Settings."""
        return settings.get_api_key(key_name)
