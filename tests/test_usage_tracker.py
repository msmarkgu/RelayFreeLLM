"""
Unit tests for UsageTracker and dispatcher usage-tracking integration.
"""

import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, AsyncMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.model_dispatcher import ModelDispatcher
from src.model_selector import ModelSelector
from src.provider_registry import ProviderRegistry
from src.exceptions import RateLimitError
from src.models import ChatCompletionRequest, ChatMessage
from src.usage_tracker import UsageTracker


class TestUsageTracker(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.tmp.write(
            '{"providers": {}, "total": {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}}'
        )
        self.tmp.close()
        self.tracker = UsageTracker(persistence_file=self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_initial_state(self):
        stats = self.tracker.get_stats()
        self.assertEqual(stats["providers"], {})
        self.assertEqual(stats["total"]["prompt_tokens"], 0)
        self.assertEqual(stats["total"]["completion_tokens"], 0)
        self.assertEqual(stats["total"]["requests"], 0)

    def test_record_single_usage(self):
        self.tracker.record_usage("Groq", "llama-3", 100, 50)
        stats = self.tracker.get_stats()

        self.assertEqual(stats["providers"]["Groq"]["models"]["llama-3"]["prompt_tokens"], 100)
        self.assertEqual(stats["providers"]["Groq"]["models"]["llama-3"]["completion_tokens"], 50)
        self.assertEqual(stats["providers"]["Groq"]["models"]["llama-3"]["requests"], 1)
        self.assertEqual(stats["providers"]["Groq"]["prompt_tokens"], 100)
        self.assertEqual(stats["providers"]["Groq"]["completion_tokens"], 50)
        self.assertEqual(stats["providers"]["Groq"]["requests"], 1)
        self.assertEqual(stats["total"]["prompt_tokens"], 100)
        self.assertEqual(stats["total"]["completion_tokens"], 50)
        self.assertEqual(stats["total"]["requests"], 1)

    def test_record_multiple_providers(self):
        self.tracker.record_usage("Groq", "llama-3", 100, 50)
        self.tracker.record_usage("Gemini", "gemini-pro", 200, 100)
        stats = self.tracker.get_stats()

        self.assertEqual(stats["providers"]["Groq"]["prompt_tokens"], 100)
        self.assertEqual(stats["providers"]["Gemini"]["prompt_tokens"], 200)
        self.assertEqual(stats["total"]["prompt_tokens"], 300)
        self.assertEqual(stats["total"]["completion_tokens"], 150)
        self.assertEqual(stats["total"]["requests"], 2)

    def test_record_multiple_models_same_provider(self):
        self.tracker.record_usage("Groq", "llama-3", 100, 50)
        self.tracker.record_usage("Groq", "mixtral", 200, 100)
        stats = self.tracker.get_stats()

        self.assertEqual(stats["providers"]["Groq"]["models"]["llama-3"]["prompt_tokens"], 100)
        self.assertEqual(stats["providers"]["Groq"]["models"]["mixtral"]["prompt_tokens"], 200)
        self.assertEqual(stats["providers"]["Groq"]["prompt_tokens"], 300)
        self.assertEqual(stats["providers"]["Groq"]["requests"], 2)

    def test_accumulation(self):
        for _ in range(5):
            self.tracker.record_usage("Groq", "llama-3", 10, 5)
        stats = self.tracker.get_stats()

        self.assertEqual(stats["providers"]["Groq"]["models"]["llama-3"]["prompt_tokens"], 50)
        self.assertEqual(stats["providers"]["Groq"]["models"]["llama-3"]["completion_tokens"], 25)
        self.assertEqual(stats["providers"]["Groq"]["models"]["llama-3"]["requests"], 5)
        self.assertEqual(stats["total"]["prompt_tokens"], 50)
        self.assertEqual(stats["total"]["requests"], 5)

    def test_get_stats_returns_copy(self):
        self.tracker.record_usage("Groq", "llama-3", 100, 50)
        stats = self.tracker.get_stats()
        stats["total"]["prompt_tokens"] = 999
        fresh = self.tracker.get_stats()
        self.assertEqual(fresh["total"]["prompt_tokens"], 100)

    def test_reset_stats(self):
        self.tracker.record_usage("Groq", "llama-3", 100, 50)
        self.tracker.reset_stats()
        stats = self.tracker.get_stats()
        self.assertEqual(stats["providers"], {})
        self.assertEqual(stats["total"]["prompt_tokens"], 0)
        self.assertEqual(stats["total"]["completion_tokens"], 0)
        self.assertEqual(stats["total"]["requests"], 0)

    def test_file_persistence(self):
        self.tracker.record_usage("Groq", "llama-3", 100, 50)
        tracker2 = UsageTracker(persistence_file=self.tmp.name)
        stats = tracker2.get_stats()

        self.assertEqual(stats["providers"]["Groq"]["models"]["llama-3"]["prompt_tokens"], 100)
        self.assertEqual(stats["total"]["requests"], 1)

    def test_reset_persists_to_file(self):
        self.tracker.record_usage("Groq", "llama-3", 100, 50)
        self.tracker.reset_stats()
        tracker2 = UsageTracker(persistence_file=self.tmp.name)
        self.assertEqual(tracker2.get_stats()["total"]["requests"], 0)

    def test_concurrent_recordings(self):
        errors = []

        def record(provider, model, pt, ct):
            try:
                for _ in range(20):
                    self.tracker.record_usage(provider, model, pt, ct)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record, args=("Groq", "llama-3", 10, 5)),
            threading.Thread(target=record, args=("Gemini", "gemini-pro", 20, 10)),
            threading.Thread(target=record, args=("Groq", "mixtral", 30, 15)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        stats = self.tracker.get_stats()
        self.assertEqual(stats["providers"]["Groq"]["models"]["llama-3"]["requests"], 20)
        self.assertEqual(stats["providers"]["Gemini"]["requests"], 20)
        self.assertEqual(stats["total"]["requests"], 60)


class _DispatcherTestBase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_registry = MagicMock(spec=ProviderRegistry)
        self.mock_selector = MagicMock(spec=ModelSelector)
        self.mock_usage_tracker = MagicMock()

        self.mock_gemini = AsyncMock()
        self.mock_groq = AsyncMock()
        self.mock_mistral = AsyncMock()
        self.mock_cerebras = AsyncMock()

        self.mock_registry.get_client.side_effect = self._get_client_side_effect
        self.mock_registry.list_providers.return_value = ["Gemini", "Groq", "Mistral", "Cerebras"]

        self.mock_selector.provider_sequence = ["Gemini", "Groq", "Mistral", "Cerebras"]
        self.mock_selector.provider_strategy = "roundrobin"

    def _get_client_side_effect(self, name):
        mapping = {
            "Gemini": self.mock_gemini,
            "Groq": self.mock_groq,
            "Mistral": self.mock_mistral,
            "Cerebras": self.mock_cerebras,
        }
        return mapping.get(name)


class TestDispatcherUsageTracking(_DispatcherTestBase):

    async def test_usage_tracker_called_on_meta_model_success(self):
        self.mock_selector.select.return_value = ("Gemini", "gemini-2.0-flash", 0.0)
        self.mock_gemini.call_model_api.return_value = "Response"
        dispatcher = ModelDispatcher(
            self.mock_registry, self.mock_selector, self.mock_usage_tracker
        )
        request = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")]
        )
        await dispatcher.chat(request)

        self.mock_usage_tracker.record_usage.assert_called_once()
        args, _ = self.mock_usage_tracker.record_usage.call_args
        provider, model = args[0], args[1]
        self.assertEqual(provider, "Gemini")
        self.assertEqual(model, "gemini-2.0-flash")

    async def test_usage_tracker_called_on_specific_routing(self):
        mock_nvidia = AsyncMock()
        mock_nvidia.call_model_api.return_value = "Response"
        self.mock_registry.get_client.side_effect = (
            lambda name: mock_nvidia if name == "Nvidia" else self._get_client_side_effect(name)
        )
        self.mock_selector.providers = {"Nvidia": MagicMock()}
        self.mock_selector.providers["Nvidia"].models = [
            MagicMock(model_name="moonshotai/kimi-k2-instruct")
        ]

        dispatcher = ModelDispatcher(
            self.mock_registry, self.mock_selector, self.mock_usage_tracker
        )
        request = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            model="groq/moonshotai/kimi-k2-instruct",
        )
        await dispatcher.chat(request)

        self.mock_usage_tracker.record_usage.assert_called_once()
        args, _ = self.mock_usage_tracker.record_usage.call_args
        provider, model = args[0], args[1]
        self.assertEqual(provider, "Nvidia")
        self.assertEqual(model, "moonshotai/kimi-k2-instruct")

    async def test_usage_tracker_not_called_on_streaming(self):
        self.mock_selector.select.return_value = ("Gemini", "gemini-2.0-flash", 0.0)
        self.mock_gemini.call_model_api.return_value = AsyncMock()
        dispatcher = ModelDispatcher(
            self.mock_registry, self.mock_selector, self.mock_usage_tracker
        )
        request = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            stream=True,
        )
        await dispatcher.chat(request)

        self.mock_usage_tracker.record_usage.assert_not_called()

    async def test_usage_tracker_not_called_on_failure(self):
        self.mock_selector.select.return_value = ("Gemini", "gemini-2.0-flash", 0.0)
        self.mock_gemini.call_model_api.side_effect = RateLimitError("Gemini", "over quota")
        dispatcher = ModelDispatcher(
            self.mock_registry, self.mock_selector, self.mock_usage_tracker
        )
        request = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")]
        )
        await dispatcher.chat(request)

        self.mock_usage_tracker.record_usage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
