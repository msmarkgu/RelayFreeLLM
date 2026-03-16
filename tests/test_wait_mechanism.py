import sys
import os
import unittest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.model_dispatcher import ModelDispatcher
from src.model_selector import ModelSelector
from src.provider_registry import ProviderRegistry
from src.api_limits_tracker import ApiLimitsTracker
from src.models import ChatCompletionRequest, ChatMessage
from src.config import settings

class TestWaitMechanism(unittest.IsolatedAsyncioTestCase):

    async def test_wait_logic_triggered(self):
        """Verify that dispatcher waits when quota is exceeded."""
        
        # 1. Setup small limits
        limits = {
            "requests_per_second": 2,
            "requests_per_minute": 10,
            "requests_per_hour": 100,
            "requests_per_day": 1000,
            "tokens_per_minute": 100, # Small TPM
            "tokens_per_hour": 1000,
            "tokens_per_day": 10000
        }
        
        tracker = ApiLimitsTracker("TestProv", "TestModel", limits)
        
        # 2. Consume some quota (60 tokens)
        tracker.record_usage(60)
        
        # 3. Try to consume 50 more (Total 110 > 100 TPM)
        # It should trigger a wait time of ~60s
        wait_time = tracker.get_wait_time(50)
        self.assertGreater(wait_time, 50)
        self.assertLessEqual(wait_time, 60)
        
        # 4. Mock Dispatcher/Selector setup
        mock_registry = MagicMock(spec=ProviderRegistry)
        mock_client = AsyncMock()
        mock_client.call_model_api.return_value = "Success response"
        mock_registry.get_client.return_value = mock_client
        
        # We'll use a real selector but point it to our tracker
        selector = ModelSelector()
        selector.providers = {
            "TestProv": MagicMock(models=[tracker], select_within=MagicMock(side_effect=lambda t, strategy: tracker.select_within(t, strategy)))
        }
        # Actually selector.providers should contain ApiProvider object
        from src.api_provider import ApiProvider
        selector.providers = {
           "TestProv": ApiProvider("TestProv", [tracker])
        }
        selector.provider_sequence = ["TestProv"]
        
        dispatcher = ModelDispatcher(mock_registry, selector)
        
        # 5. Patch asyncio.sleep to avoid actual waiting
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            request = ChatCompletionRequest(messages=[ChatMessage(role="user", content="Hello")])
            
            # First attempt should wait, then retry and succeed (because we mock selector/tracker behavior)
            # Wait, tracker.can_handle will still return False unless we advance time or cleanup manually.
            # In the retry loop, can_handle is called again.
            
            # To make the test faster/predictable, we'll mock tracker.can_handle 
            # to return False then True.
            with patch.object(tracker, 'can_handle', side_effect=[False, True]):
                # And mock get_wait_time to return a specific value
                with patch.object(tracker, 'get_wait_time', return_value=10.0):
                    response = await dispatcher.chat(request)
                    
            # Verify sleep was called
            mock_sleep.assert_called_once_with(10.0)
            self.assertEqual(response.choices[0].message.content, "Success response")

    async def test_wait_exceeds_max(self):
        """Verify that dispatcher fails if wait time is too long."""
        limits = {
            "requests_per_second": 1,
            "requests_per_minute": 1,
            "requests_per_hour": 1,
            "requests_per_day": 10,
            "tokens_per_minute": 100,
            "tokens_per_hour": 100,
            "tokens_per_day": 100
        }
        tracker = ApiLimitsTracker("TestProv", "TestModel", limits)
        
        # Max wait is 3600 by default. Let's mock a wait of 4000
        mock_selector = MagicMock(spec=ModelSelector)
        mock_selector.select.return_value = ("TestProv", "", 4000.0)
        
        dispatcher = ModelDispatcher(MagicMock(), mock_selector)
        request = ChatCompletionRequest(messages=[ChatMessage(role="user", content="Hello")])
        
        response = await dispatcher.chat(request)
        self.assertIn("exceeds limit", response.choices[0].message.content)

if __name__ == "__main__":
    unittest.main()
