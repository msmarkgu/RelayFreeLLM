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

    @abstractmethod
    async def call_model_api(
        self,
        user_prompt: str,
        model: str,
        sys_instruct: str,
        temperature: float,
        max_tokens: int,
        stream: bool = False,
    ) -> str | object:
        pass

    @abstractmethod
    async def list_models(self) -> list[str]:
        pass

    @staticmethod
    def load_api_key(key_name: str) -> str:
        """Load an API key from environment variables via Settings."""
        return settings.get_api_key(key_name)
