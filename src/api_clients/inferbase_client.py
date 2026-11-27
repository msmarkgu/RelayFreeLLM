"""Inferbase AI gateway client (OpenAI-compatible).

Inferbase exposes OpenAI-compatible chat completions at ``/v1`` and a public
model catalog at ``/v1/models``. A free API key has no rate-limit surprises
beyond the documented plan caps: 5,000 requests/month, 100 managed requests
and $0.50 of managed usage/day, with 8,192 input and 1,024 output tokens per
request. Tool calls and SSE streaming are passed through natively.
"""

from .openai_compatible_client import OpenAICompatibleClient


class InferbaseClient(OpenAICompatibleClient):
    PROVIDER_NAME = "Inferbase"
    KEY_NAME = "INFERBASE_APIKEY"
    BASE_URL = "https://api.inferbase.ai/v1"
    # GET /models is public; chat completions require the API key.
    MODELS_REQUIRE_AUTH = False
