"""Routeway gateway client (OpenAI-compatible, free models only).

Routeway's free Starter plan requires a free API key but no credit card and
allows 200 requests/day on model ids ending in ``:free`` (5 RPM). Pay-as-you-go
model IDs and uncurated free models are intentionally not exposed; the client
filters ``/models`` down to its curated Gemma 4 26B free finetunes. Tools and
SSE streaming use the standard OpenAI format.
"""

from .openai_compatible_client import OpenAICompatibleClient


class RoutewayClient(OpenAICompatibleClient):
    PROVIDER_NAME = "Routeway"
    KEY_NAME = "ROUTEWAY_APIKEY"
    BASE_URL = "https://api.routeway.ai/v1"
    # GET /models is public; chat completions require the API key.
    MODELS_REQUIRE_AUTH = False
    # Routeway advertises more free IDs than the gateway curates. Keep only the
    # five Gemma 4 26B finetunes that are enabled in the registry.
    CURATED_MODEL_IDS = (
        "gemma-4-26b-a4b-it-chimerax:free",
        "gemma-4-26b-a4b-it-luminous:free",
        "gemma-4-26b-a4b-it-moonlight:free",
        "gemma-4-26b-a4b-it-musica:free",
        "gemma-4-26b-a4b-it-meromero:free",
    )

    async def list_models(self) -> list[str]:
        models = await super().list_models()
        return [model for model in models if model in self.CURATED_MODEL_IDS]
