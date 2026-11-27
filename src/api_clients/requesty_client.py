"""Requesty gateway client (OpenAI-compatible)."""

from .openai_compatible_client import OpenAICompatibleClient


class RequestyClient(OpenAICompatibleClient):
    PROVIDER_NAME = "Requesty"
    KEY_NAME = "REQUESTY_APIKEY"
    BASE_URL = "https://router.requesty.ai/v1"
    # Managed policy IDs are usable directly as models and include the free
    # tiers; fall back to the generic model list if that endpoint fails.
    MODELS_PATHS = ("/models/managed", "/models")
