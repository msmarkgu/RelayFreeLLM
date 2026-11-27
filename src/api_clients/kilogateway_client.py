"""Kilo Gateway free-tier client (OpenAI-compatible, anonymous).

Kilo allows unauthenticated inference for model ids ending in ``:free`` and
for the ``kilo-auto/free`` virtual model (200 requests/hour/IP). Paid models
require an API key, so this client keeps the provider free-only and filters
its model list accordingly.
"""

from .openai_compatible_client import OpenAICompatibleClient


class KiloGatewayClient(OpenAICompatibleClient):
    PROVIDER_NAME = "KiloGateway"
    REQUIRES_API_KEY = False
    BASE_URL = "https://ai-gateway.kilo.ai/api/v1"
    # GET /models is public; anonymous chat completions work for :free models.
    MODELS_REQUIRE_AUTH = False
    # Virtual free tiers do not use the :free suffix but are also anonymous.
    EXTRA_MODEL_IDS = ("kilo-auto/free",)

    async def list_models(self) -> list[str]:
        models = await super().list_models()
        return [
            model
            for model in models
            if model.endswith(":free") or model in self.EXTRA_MODEL_IDS
        ]
