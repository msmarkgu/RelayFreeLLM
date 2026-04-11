import asyncio
import time
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.config import settings
from src.model_dispatcher import ModelDispatcher
from src.api_clients.api_interface import ApiInterface

class MockClient(ApiInterface):
    PROVIDER_NAME = "Mock"
    async def list_models(self): return ["mock-model"]
    async def call_model_api(self, **kwargs):
        print(f"  [Mock] Call started at {time.time() % 100:.2f}")
        await asyncio.sleep(2) # Simulate work
        print(f"  [Mock] Call finished at {time.time() % 100:.2f}")
        return "mock response"

class MockRegistry:
    def get_client(self, name):
        return MockClient()
    def list_providers(self):
        return ["Mock"]

async def test_global_lock():
    print(f"Testing Global Provider Lock (GLOBAL_PROVIDER_LOCK={settings.GLOBAL_PROVIDER_LOCK})...")
    
    # Setup Mock Registry and Dispatcher
    registry = MockRegistry()
    # Selector isn't used in call_provider_api directly for routing logic, 
    # but Dispatcher init needs it.
    dispatcher = ModelDispatcher(registry, None) 
    
    # Ensure the lock is initialized for the Mock provider
    dispatcher.provider_locks["Mock"] = asyncio.Lock()
    
    async def call_meta(i):
        print(f"Request {i} dispatched at {time.time() % 100:.2f}")
        await dispatcher.call_provider_api(
            provider_name="Mock",
            model_name="mock-model",
            user_prompt="hi",
            system_prompt="",
            session_id=f"test-{i}"
        )
        print(f"Request {i} completed at {time.time() % 100:.2f}")

    start = time.time()
    # Run 3 requests concurrently
    await asyncio.gather(call_meta(1), call_meta(2), call_meta(3))
    total = time.time() - start
    
    print(f"\nTotal time: {total:.2f}s")
    if settings.GLOBAL_PROVIDER_LOCK:
        if total >= 5.8: # Should be ~6s (3 * 2s)
            print("SUCCESS: Requests executed serially.")
        else:
            print("FAILURE: Requests executed in parallel despite lock.")
    else:
        if total < 3: # Should be ~2s (all start at once)
            print("SUCCESS: Requests executed in parallel (lock disabled).")
        else:
            print("INFO: Requests were slower than expected.")

if __name__ == "__main__":
    # Ensure lock is enabled for this test
    os.environ["GLOBAL_PROVIDER_LOCK"] = "True"
    # Re-initialize settings to pick up the ENV override
    from src.config import Settings
    import src.config
    src.config.settings = Settings()
    
    asyncio.run(test_global_lock())
