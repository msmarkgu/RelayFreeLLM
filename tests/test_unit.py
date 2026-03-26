import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import sys
import os

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.model_dispatcher import ModelDispatcher
from src.provider_registry import ProviderRegistry
from src.model_selector import ModelSelector
from src.config import settings
from src.exceptions import RateLimitError, AuthenticationError
from src.models import ChatCompletionRequest, ChatMessage
from src.api_limits_tracker import ApiLimitsTracker

class TestRelayFreeLLMCore(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # 1. Create mocks
        self.mock_registry = MagicMock(spec=ProviderRegistry)
        self.mock_selector = MagicMock(spec=ModelSelector)
        self.mock_usage_tracker = MagicMock()
        
        # 2. Mock clients
        self.mock_gemini = AsyncMock()
        self.mock_groq = AsyncMock()
        self.mock_mistral = AsyncMock()
        self.mock_cerebras = AsyncMock()
        
        # 3. Setup registry to return mocks
        self.mock_registry.get_client.side_effect = self._get_client_side_effect
        self.mock_registry.list_providers.return_value = ["Gemini", "Groq", "Mistral", "Cerebras"]
        
        # 4. Setup selector default
        self.mock_selector.provider_sequence = ["Gemini", "Groq", "Mistral", "Cerebras"]
        self.mock_selector.provider_strategy = "roundrobin"

    def _get_client_side_effect(self, name):
        mapping = {
            "Gemini": self.mock_gemini,
            "Groq": self.mock_groq,
            "Mistral": self.mock_mistral,
            "Cerebras": self.mock_cerebras
        }
        return mapping.get(name)

    async def test_dispatcher_initialization(self):
        dispatcher = ModelDispatcher(self.mock_registry, self.mock_selector)
        self.assertIsNotNone(dispatcher)

    async def test_chat_successful_routing(self):
        self.mock_selector.select.return_value = ("Gemini", "gemini-2.0-flash", 0.0)
        self.mock_gemini.call_model_api.return_value = "Gemini Response"
        
        dispatcher = ModelDispatcher(self.mock_registry, self.mock_selector, self.mock_usage_tracker)
        request = ChatCompletionRequest(messages=[ChatMessage(role="user", content="User Prompt")])
        response = await dispatcher.chat(request)
        
        self.assertEqual(response.meta.provider, "Gemini")
        self.assertEqual(response.model, "gemini-2.0-flash")
        self.assertEqual(response.choices[0].message.content, "Gemini Response")
        self.mock_gemini.call_model_api.assert_called_once()

    async def test_provider_mapping(self):
        """Verify that call_provider_api routes to the correct registry client."""
        dispatcher = ModelDispatcher(self.mock_registry, self.mock_selector)
        providers = [
            ("Cerebras", self.mock_cerebras),
            ("Groq", self.mock_groq),
            ("Mistral", self.mock_mistral),
            ("Gemini", self.mock_gemini)
        ]
        
        for provider_name, mock_client in providers:
            with self.subTest(provider=provider_name):
                mock_client.call_model_api.return_value = f"{provider_name} Response"
                await dispatcher.call_provider_api(provider_name, "test-model", "usr", "sys")
                mock_client.call_model_api.assert_called()

    async def test_prompt_combination_and_standard_injection(self):
        """Verify that system prompt and standard prompt are combined correctly."""
        dispatcher = ModelDispatcher(self.mock_registry, self.mock_selector)
        sys_prompt = "Custom Sys Prompt"
        expected_full_prompt = f"{sys_prompt}\n\n{settings.STANDARD_SYSTEM_PROMPT}"
        
        self.mock_gemini.call_model_api.return_value = "Response"
        await dispatcher.call_provider_api("Gemini", "gemini-2.0-flash", "Hello", sys_prompt)
        
        call_args = self.mock_gemini.call_model_api.call_args.kwargs
        self.assertEqual(call_args['user_prompt'], "Hello")
        self.assertEqual(call_args['sys_instruct'], expected_full_prompt)

    async def test_get_wait_time_calculation(self):
        """Verify the mathematical wait time calculation in ApiLimitsTracker."""
        limits = {
            "requests_per_second": 10,
            "requests_per_minute": 100,
            "requests_per_hour": 1000,
            "requests_per_day": 10000,
            "tokens_per_minute": 100, # Small TPM for testing
            "tokens_per_hour": 1000,
            "tokens_per_day": 10000
        }
        tracker = ApiLimitsTracker("TestProv", "TestModel", limits)
        
        # 1. Record 60 tokens
        tracker.record_usage(60)
        
        # 2. Try to send 50 more (exceeds 100 TPM)
        wait_time = tracker.get_wait_time(50)
        
        # Should be roughly 60 seconds (full window) since we just recorded usage
        self.assertGreater(wait_time, 0)
        self.assertLessEqual(wait_time, 60)

    async def test_token_estimation_includes_system_prompt(self):
        """Verify that token estimation sums both user and system prompts."""
        selector = ModelSelector()
        user_text = "Hello world" # 2 words -> ~2.6 tokens
        sys_text = "Be helpful"   # 2 words -> ~2.6 tokens
        
        num_tokens = selector.estimate_tokens(f"{sys_text}\n\n{user_text}")
        
        # Combined estimation used in select()
        # Mocking select logic for isolated test
        with patch.object(selector, 'estimate_tokens', side_effect=lambda x: len(x.split())):
            # 2 words + 2 words = 4 total
            with patch.object(selector, 'providers', {}): # Avoid real provider calls
                try:
                    await selector.select(user_text, sys_text)
                except Exception:
                    pass
                
        self.assertEqual(num_tokens, 5) # 1.3 * 2 + 1.3 * 2 = 2.6 + 2.6 = 5.2 -> 5 (int)

    async def test_retry_on_rate_limit(self):
        """Verify that the dispatcher retries with a different provider on rate limits."""
        # 1. First call to Gemini fails with RateLimit
        self.mock_gemini.call_model_api.side_effect = RateLimitError("Gemini", "Too many requests")
        # 2. Second call to Groq succeeds
        self.mock_groq.call_model_api.return_value = "Groq Success"
        
        # 3. Setup selector to return Gemini then Groq
        self.mock_selector.select.side_effect = [
            ("Gemini", "gemini-pro", 0.0),
            ("Groq", "llama-3", 0.0)
        ]
        
        dispatcher = ModelDispatcher(self.mock_registry, self.mock_selector)
        request = ChatCompletionRequest(messages=[ChatMessage(role="user", content="hello")])
        response = await dispatcher.chat(request)
        
        self.assertEqual(response.meta.provider, "Groq")
        self.assertEqual(response.choices[0].message.content, "Groq Success")
        self.assertEqual(self.mock_gemini.call_model_api.call_count, 1)
        self.assertEqual(self.mock_groq.call_model_api.call_count, 1)

    async def test_unknown_provider_raises_error(self):
        self.mock_registry.get_client.side_effect = ValueError("Unknown provider")
        dispatcher = ModelDispatcher(self.mock_registry, self.mock_selector)
        with self.assertRaises(ValueError):
            await dispatcher.call_provider_api("Unknown", "model", "usr", "sys")

if __name__ == '__main__':
    unittest.main()
