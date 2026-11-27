"""Case-insensitive provider prefixes for specific routing."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

from src.api_clients.api_interface import ApiInterface
from src.model_dispatcher import ModelDispatcher
from src.models import ChatCompletionRequest, ChatMessage
from src.provider_registry import ProviderRegistry


class DummyClient(ApiInterface):
    PROVIDER_NAME = "Groq"

    async def list_models(self):
        return ["qwen/qwen3.8-27b"]

    async def call_model_api(self, **kwargs):
        return "ok"


class TestSpecificRoutingProviderCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        registry = ProviderRegistry()
        registry.register("Groq", DummyClient())

        selector = MagicMock()
        selector.providers = {
            "Groq": SimpleNamespace(
                models=[SimpleNamespace(model_name="qwen/qwen3.8-27b")]
            )
        }
        selector.estimate_tokens.return_value = 1

        self.dispatcher = ModelDispatcher(registry, selector, None)
        self.dispatcher.call_provider_api = AsyncMock(return_value="ok")

    async def test_lower_case_provider_prefix_matches_registered_client(self):
        request = ChatCompletionRequest(
            model="groq/qwen/qwen3.8-27b",
            messages=[ChatMessage(role="user", content="hello")],
        )

        response = await self.dispatcher.chat(request)

        self.assertIsNone(response.error)
        self.assertEqual(
            self.dispatcher.call_provider_api.await_args.kwargs["provider_name"],
            "Groq",
        )
        self.assertEqual(
            self.dispatcher.call_provider_api.await_args.kwargs["model_name"],
            "qwen/qwen3.8-27b",
        )


class TestProviderOutputTokenCap(unittest.IsolatedAsyncioTestCase):
    async def test_client_cap_is_applied_before_upstream_call(self):
        client = MagicMock()
        client.max_output_tokens_cap = 16384
        client.call_model_api = AsyncMock(return_value="ok")

        registry = MagicMock()
        registry.get_client.return_value = client

        selector = MagicMock()
        selector.providers = {
            "Groq": SimpleNamespace(
                models=[SimpleNamespace(model_name="qwen/qwen3.8-27b")]
            )
        }

        dispatcher = ModelDispatcher(registry, selector, None)
        await dispatcher.call_provider_api(
            provider_name="Groq",
            model_name="qwen/qwen3.8-27b",
            user_prompt="hello",
            system_prompt="",
            max_tokens=64000,
        )

        self.assertEqual(
            client.call_model_api.await_args.kwargs["max_tokens"], 16384
        )


if __name__ == "__main__":
    unittest.main()
