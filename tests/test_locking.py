import asyncio
import time
import unittest
import os
import sys
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from src.config import settings
from src.model_dispatcher import ModelDispatcher
from src.api_clients.api_interface import ApiInterface

class MockApiClient(ApiInterface):
    """A client that simulates work with a configurable delay."""
    def __init__(self, delay=0.5):
        self.delay = delay
        self.call_count = 0

    async def list_models(self):
        return ["mock-model"]

    async def call_model_api(self, **kwargs):
        self.call_count += 1
        await asyncio.sleep(self.delay)
        return "mocked response content"

class TestGlobalProviderLock(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Save original setting
        self.original_lock_setting = settings.GLOBAL_PROVIDER_LOCK
        
        # Setup mocks
        self.registry = MagicMock()
        self.selector = MagicMock()
        self.usage_tracker = MagicMock()
        
        # Create dispatcher
        self.dispatcher = ModelDispatcher(self.registry, self.selector, self.usage_tracker)
        
        # Register mock client
        self.mock_client = MockApiClient(delay=0.5)
        self.registry.get_client.return_value = self.mock_client

    async def asyncTearDown(self):
        # Restore original setting
        settings.GLOBAL_PROVIDER_LOCK = self.original_lock_setting

    async def test_lock_enabled_serializes_requests(self):
        """Verify that when lock is ENABLED, requests are serialized."""
        settings.GLOBAL_PROVIDER_LOCK = True
        
        # Ensure lock exists for the Mock provider
        self.dispatcher.provider_locks["Mock"] = asyncio.Lock()
        
        # Launch two requests concurrently
        start_time = time.time()
        await asyncio.gather(
            self.dispatcher.call_provider_api("Mock", "m", "hi", ""),
            self.dispatcher.call_provider_api("Mock", "m", "hi", "")
        )
        duration = time.time() - start_time
        
        # With 0.5s delay, serial execution should take >= 1.0s
        self.assertGreaterEqual(duration, 1.0)
        self.assertEqual(self.mock_client.call_count, 2)

    async def test_lock_disabled_allows_parallel_requests(self):
        """Verify that when lock is DISABLED, requests run in parallel."""
        settings.GLOBAL_PROVIDER_LOCK = False
        
        # Launch two requests concurrently
        start_time = time.time()
        await asyncio.gather(
            self.dispatcher.call_provider_api("Mock", "m", "hi", ""),
            self.dispatcher.call_provider_api("Mock", "m", "hi", "")
        )
        duration = time.time() - start_time
        
        # With 0.5s delay, parallel execution should take ~0.5s (definitely < 1.0s)
        self.assertLess(duration, 0.9)
        self.assertEqual(self.mock_client.call_count, 2)

if __name__ == "__main__":
    unittest.main()
