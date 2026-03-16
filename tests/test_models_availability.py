import asyncio
import json
import logging
import os
import sys

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from src.provider_registry import ProviderRegistry
from src.logging_util import ProjectLogger
from src.config import settings

# Configure logging to console only for this test
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ModelChecker")

async def test_model(registry, provider_name, model_name):
    """Test a single model's availability."""
    try:
        client = registry.get_client(provider_name)
        logger.info(f"Testing {provider_name} - {model_name}...")

        # Simple probe request
        response = await client.call_model_api(
            user_prompt="Hi, introduce yourself.",
            model=model_name,
            sys_instruct="Be brief.",
            temperature=0.1,
            max_tokens=1000
        )

        if response:
            logger.info(f"✅ {provider_name} - {model_name}: SUCCESS")
            return (provider_name, model_name, True, "Success")
        else:
            logger.error(f"❌ {provider_name} - {model_name}: EMPTY RESPONSE")
            return (provider_name, model_name, False, "Empty response")

    except Exception as e:
        logger.error(f"❌ {provider_name} - {model_name}: FAILED - {str(e)}")
        return (provider_name, model_name, False, str(e))

async def main():
    # 1. Load limits JSON to get models
    registry_path = settings.REGISTRY_FILE
    with open(registry_path, "r") as f:
        data = json.load(f)

    # 2. Initialize registry
    registry = ProviderRegistry()
    registry.auto_discover()

    tasks = []
    for provider_data in data["providers"]:
        provider_name = provider_data["name"]

        # Skip DeepSeek if no key is found (to avoid expected failure in logs)
        try:
            settings.get_api_key(f"{provider_name.upper()}_APIKEY")
        except ValueError:
            logger.warning(f"Skipping {provider_name} due to missing API key.")
            continue

        for model_data in provider_data["models"]:
            model_name = model_data["name"]
            tasks.append(test_model(registry, provider_name, model_name))

    if not tasks:
        logger.error("No models found or no API keys configured.")
        return

    logger.info(f"Starting availability test for {len(tasks)} models...")
    results = await asyncio.gather(*tasks)

    # 3. Print Summary
    print("\n" + "="*50)
    print("MODEL AVAILABILITY SUMMARY")
    print("="*50)
    success_count = 0
    for prov, model, ok, msg in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status} | {prov:12} | {model:40} | {msg}")
        if ok:
            success_count += 1

    print("="*50)
    print(f"TOTAL: {success_count}/{len(results)} models available.")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
