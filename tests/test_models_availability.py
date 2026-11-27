import argparse
import asyncio
import json
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from src.provider_registry import ProviderRegistry
from src.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ModelChecker")


async def _test_model(
    registry, provider_name, model_name, limiter, delay=0.0
):
    """Test a single model's availability, serialised per provider."""
    async with limiter:
        try:
            client = registry.get_client(provider_name)
            logger.info(f"\nTesting {provider_name} - {model_name}...")

            response = await client.call_model_api(
                messages=[
                    {"role": "system", "content": "Be brief."},
                    {"role": "user", "content": "Hi, introduce yourself."}
                ],
                model=model_name,
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
        finally:
            # Hold the provider's semaphore during the gap so calls to the same
            # provider never overlap. Providers remain free to run in parallel.
            if delay > 0:
                await asyncio.sleep(delay)


async def main():
    parser = argparse.ArgumentParser(description="Test model availability for providers")
    parser.add_argument(
        "provider",
        nargs="?",
        default=None,
        help="Provider name to test (e.g., 'Nvidia', 'Groq'). If not specified, tests all providers."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between calls to the same provider (default: 2.0).",
    )
    args = parser.parse_args()

    registry_path = settings.REGISTRY_FILE
    with open(registry_path, "r") as f:
        data = json.load(f)

    registry = ProviderRegistry()
    registry.auto_discover()

    available_providers = [p["name"] for p in data["providers"]]

    if args.provider:
        provider_lower = args.provider.lower()
        provider_map = {p.lower(): p for p in available_providers}
        if provider_lower not in provider_map:
            logger.error(f"Unknown provider: {args.provider}")
            logger.info(f"Available providers: {', '.join(available_providers)}")
            sys.exit(1)
        providers_to_test = [provider_map[provider_lower]]
    else:
        providers_to_test = available_providers

    logger.info(
        "Serialising calls per provider with a %.1fs gap; providers still run in parallel.",
        args.delay,
    )
    limiters = {provider: asyncio.Semaphore(1) for provider in providers_to_test}
    tasks = []
    for provider_data in data["providers"]:
        provider_name = provider_data["name"]

        if provider_name not in providers_to_test:
            continue

        if provider_data.get("enabled", True) is False:
            logger.info(f"Skipping disabled provider {provider_name}.")
            continue

        try:
            api_key_name = f"{provider_name.upper()}_APIKEY"
            if provider_name == "Ollama":
                settings.get_api_key("OLLAMA_BASE_URL")
            elif provider_name == "KiloGateway":
                # Kilo's :free models work anonymously; no key is configured.
                pass
            else:
                settings.get_api_key(api_key_name)
        except ValueError:
            logger.warning(f"Skipping {provider_name} due to missing API key.")
            continue

        for model_data in provider_data["models"]:
            model_name = model_data["name"]
            tasks.append(
                _test_model(
                    registry,
                    provider_name,
                    model_name,
                    limiters[provider_name],
                    args.delay,
                )
            )

    if not tasks:
        logger.error("No models found or no API keys configured.")
        return

    logger.info(f"Starting availability test for {len(tasks)} models...")
    results = await asyncio.gather(*tasks)

    print("\n" + "=" * 70)
    print("MODEL AVAILABILITY SUMMARY")
    print("=" * 70)
    success_count = 0
    for prov, model, ok, msg in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status} | {prov:15} | {model:45} | {msg}")
        if ok:
            success_count += 1

    print("=" * 70)
    print(f"TOTAL: {success_count}/{len(results)} models available.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
