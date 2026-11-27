"""DreamPrompting gateway client (OpenAI-compatible).

DreamPrompting provides a free account API key, routes each request across
several upstream providers, and supports OpenAI-compatible tool calling and
streaming. Its ``auto`` model fails over between live providers and is curated
in ``provider_model_limits.json`` even though it does not appear in /models.
"""

from .openai_compatible_client import OpenAICompatibleClient


class DreamPromptingClient(OpenAICompatibleClient):
    PROVIDER_NAME = "DreamPrompting"
    KEY_NAME = "DREAMPROMPTING_APIKEY"
    BASE_URL = "https://dreamprompting.com/api/v1"
