"""
Model Selector — rate-limit-aware provider and model selection.

Supports multiple selection strategies at both provider and model level.
No singleton pattern; lifecycle managed by FastAPI lifespan.
"""

import json
import os
import random
import time

from .api_limits_tracker import ApiLimitsTracker
from .api_provider import ApiProvider
from .config import settings
from .logging_util import ProjectLogger

CUR_DIR = os.path.dirname(os.path.realpath(__file__))


class ModelSelector:

    DEFAULT_LIMITS = {
        "requests_per_second": 1,
        "requests_per_minute": 5,
        "requests_per_hour": 60,
        "requests_per_day": 100,
        "tokens_per_minute": 250000,
        "tokens_per_hour": -1,
        "tokens_per_day": -1
    }

    def __init__(
        self,
        provider_sequence: list[str] = None,
        provider_strategy: str = None,
        model_strategy: str = None,
    ):
        self.logger = ProjectLogger.get_logger(__name__)
        self.registry_file = settings.REGISTRY_FILE
        self.providers = self.load_api_limits_from_json(self.registry_file)

        self.logger.info("Providers: %s", self.providers)

        self.provider_sequence = provider_sequence or list(self.providers.keys())
        self.provider_strategy = provider_strategy or settings.PROVIDER_STRATEGY
        self.model_strategy = model_strategy or settings.MODEL_STRATEGY
        self.last_provider_index = -1

        self.logger.info(
            "Provider sequence: %s, Provider Strategy: %s, Model Strategy: %s",
            self.provider_sequence, self.provider_strategy, self.model_strategy,
        )

    def load_api_limits_from_json(self, path: str) -> dict[str, ApiProvider]:
        with open(path, "r") as f:
            data = json.load(f)

        providers = {}
        for prov in data["providers"]:
            provider_name = prov["name"]
            models = [
                ApiLimitsTracker(provider_name, m["name"], m["limits"])
                for m in prov["models"]
            ]
            providers[provider_name] = ApiProvider(provider_name, models)

        return providers

    def estimate_tokens(self, text):
        # Simplified token estimate: 1 word ≈ 1.3 tokens
        return int(len(text.split()) * 1.3)

    def select(
        self,
        user_input: str,
        system_prompt: str = "",
        preferred_provider: str = None,
        exclude_providers: list[str] = None,
    ) -> tuple[str, str, float]:
        """Select a provider's model for the given user input and system prompt. Returns (provider, model, wait_time)."""
        num_of_tokens = self.estimate_tokens(user_input) + self.estimate_tokens(system_prompt)
        exclude_set = set(exclude_providers) if exclude_providers else set()

        if preferred_provider and preferred_provider in self.providers and preferred_provider not in exclude_set:
            search_order = [preferred_provider] + [
                p for p in self.provider_sequence if p != preferred_provider and p not in exclude_set
            ]
        elif self.provider_strategy == "random":
            search_order = [p for p in self.provider_sequence if p not in exclude_set]
            random.shuffle(search_order)
        else:  # roundrobin
            if self.last_provider_index == -1:
                usable_indices = [
                    i for i, p in enumerate(self.provider_sequence) if p not in exclude_set
                ]
                if not usable_indices:
                    # If all are excluded, still return something or raise? 
                    # For wait mechanism, we might want to know the wait time even if excluded?
                    # No, exclude means exclude.
                    raise RuntimeError("No available providers match selection criteria.")
                self.last_provider_index = random.choice(usable_indices)

            search_order = []
            for i in range(len(self.provider_sequence)):
                index = (self.last_provider_index + i + 1) % len(self.provider_sequence)
                prov = self.provider_sequence[index]
                if prov not in exclude_set:
                    search_order.append(prov)

        min_wait_time = float('inf')
        best_candidate = None

        for prov_name in search_order:
            provider = self.providers[prov_name]
            model, wait_time = provider.select_within(num_of_tokens, strategy=self.model_strategy)
            
            if model:
                if prov_name in self.provider_sequence:
                    self.last_provider_index = self.provider_sequence.index(prov_name)
                return prov_name, model.model_name, 0.0
            
            if wait_time < min_wait_time:
                min_wait_time = wait_time
                best_candidate = (prov_name, "wait") # generic indicator

        if best_candidate:
            # Re-scan for the actual model name that has the min wait time in that provider
            # This is slightly inefficient but keeps the select_within return simple
            # Actually let's just picking the prov_name and a placeholder is fine, 
            # the dispatcher will just wait and call select again.
            return best_candidate[0], "", min_wait_time

        raise RuntimeError("All models in all providers are at capacity. Try later.")

    def get_model_providers(self) -> dict[str, ApiProvider]:
        return self.providers

    def trigger_circuit_breaker(self, provider_name: str, model_name: str, duration_sec: int = 300):
        """Put a specific model into cooldown."""
        if provider_name in self.providers:
            provider = self.providers[provider_name]
            for model in provider.models:
                if model.model_name == model_name:
                    model.trigger_cooldown(duration_sec)
                    self.logger.warning(f"Circuit breaker triggered for {provider_name}/{model_name} for {duration_sec}s")
                    return
        self.logger.error(f"Could not find model {provider_name}/{model_name} to trigger circuit breaker.")

    def get_model_usage(self) -> dict:
        stats = {}
        for prov_name, provider in self.providers.items():
            stats[prov_name] = provider.usage_counter
        return stats

    def get_available_models(self) -> dict:
        available_models = []
        aggregate_limits = {
            "requests_per_second": 0,
            "requests_per_minute": 0,
            "requests_per_hour": 0,
            "requests_per_day": 0,
            "tokens_per_minute": 0,
            "tokens_per_hour": 0,
            "tokens_per_day": 0
        }

        for prov_name, provider in self.providers.items():
            provider_data = {
                "provider": prov_name,
                "models": []
            }
            for model in provider.models:
                provider_data["models"].append({
                    "name": model.model_name,
                    "limits": model.limits
                })
                for limit_key in aggregate_limits:
                    limit_val = model.limits.get(limit_key, 0)
                    if limit_val != -1:
                        aggregate_limits[limit_key] += limit_val
                    else:
                        aggregate_limits[limit_key] = -1

            available_models.append(provider_data)

        return {
            "models": available_models,
            "aggregate_limits": aggregate_limits
        }

    def get_model_statuses(self) -> dict:
        """Get the current availability status of all models."""
        statuses = {}
        now = time.time()
        for prov_name, provider in self.providers.items():
            statuses[prov_name] = {}
            for model in provider.models:
                in_cooldown = now < model.cooldown_until
                statuses[prov_name][model.model_name] = {
                    "status": "cooldown" if in_cooldown else "available",
                    "cooldown_remaining": max(0, int(model.cooldown_until - now)) if in_cooldown else 0
                }
        return statuses

    def refresh_registry(self, discovered_models: dict[str, list[str]]):
        """Update the internal registry with top-10 discovered models per provider."""
        self.logger.info("Refreshing model registry with top-10 discovered models...")

        NON_TEXT_KEYWORDS = [
            "embed", "embedding", "whisper", "ocr", "moderation",
            "rerank", "speech", "stt", "tts", "vision", "image", "video",
            "guard", "safeguard", "pixtral", "voxtral"
        ]

        def is_text_gen(name: str) -> bool:
            name_lower = name.lower()
            return not any(kw in name_lower for kw in NON_TEXT_KEYWORDS)

        def score_model(name: str) -> int:
            name_lower = name.lower()
            score = 0
            if "latest" in name_lower: score += 100
            if "pro" in name_lower: score += 50
            if "large" in name_lower: score += 40
            if "reasoner" in name_lower: score += 40
            if "flash" in name_lower: score += 30
            if "turbo" in name_lower: score += 20
            if "small" in name_lower: score -= 10
            if "lite" in name_lower: score -= 20
            return score

        for provider_name, model_list in discovered_models.items():
            if not model_list:
                self.logger.warning(
                    f"No models discovered for {provider_name}. Skipping refresh to preserve existing registry."
                )
                continue

            text_models = [m for m in model_list if is_text_gen(m)]

            if provider_name not in self.providers:
                self.logger.warning(f"New provider detected: {provider_name}. Initializing...")
                self.providers[provider_name] = ApiProvider(provider_name, [])

            provider = self.providers[provider_name]

            ranked_discovery = sorted(
                text_models,
                key=lambda m: (score_model(m), m),
                reverse=True
            )
            top_10_discovered = ranked_discovery[:10]
            top_10_set = set(top_10_discovered)

            original_models = provider.models
            provider.models = [m for m in original_models if m.model_name in top_10_set]
            pruned_count = len(original_models) - len(provider.models)
            if pruned_count > 0:
                self.logger.info(f"Pruned {pruned_count} models for {provider_name} (no longer in top 10).")

            existing_names = {m.model_name for m in provider.models}
            for model_name in top_10_discovered:
                if model_name not in existing_names:
                    self.logger.info(f"Adding new top-10 model for {provider_name}: {model_name}")
                    new_tracker = ApiLimitsTracker(provider_name, model_name, self.DEFAULT_LIMITS.copy())
                    provider.models.append(new_tracker)

        self.provider_sequence = list(self.providers.keys())
        self.save_registry_to_json()

    def save_registry_to_json(self):
        """Serialize current providers and models back to the registry file."""
        data = {"providers": []}
        for provider_name, provider in self.providers.items():
            prov_data = {
                "name": provider_name,
                "url": "",
                "models": []
            }
            for model in provider.models:
                prov_data["models"].append({
                    "name": model.model_name,
                    "limits": model.limits
                })
            data["providers"].append(prov_data)

        try:
            with open(self.registry_file, "w") as f:
                json.dump(data, f, indent=2)
            self.logger.info(f"Model registry persisted to {self.registry_file}")
        except Exception as e:
            self.logger.error(f"Failed to save model registry: {e}")
