"""
Model Dispatcher — the core of the meta model.

Handles provider selection, retry logic with fallback,
and produces OpenAI-compatible responses.
"""

import asyncio
import time
import traceback

from .config import settings
from .exceptions import (
    ProviderError,
    RateLimitError,
    AuthenticationError,
    AllProvidersExhaustedError,
)
from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    build_response,
    build_error_response,
)
from .model_selector import ModelSelector
from .provider_registry import ProviderRegistry
from .logging_util import ProjectLogger


class ModelDispatcher:
    def __init__(
        self,
        registry: ProviderRegistry,
        selector: ModelSelector,
        usage_tracker: object = None,
    ):
        self.registry = registry
        self.selector = selector
        self.usage_tracker = usage_tracker
        self.logger = ProjectLogger.get_logger(__name__)

        # Sync: only keep providers in the selector that the registry can serve
        registered = set(registry.list_providers())
        selector_provs = list(selector.provider_sequence)
        removed = [p for p in selector_provs if p not in registered]
        if removed:
            self.logger.warning(
                f"Removing unregistered providers from selector: {removed}"
            )
            selector.provider_sequence = [p for p in selector_provs if p in registered]

    # ── Primary "meta model" entry point (OpenAI-compatible) ────────

    async def chat(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse | object:
        """
        The meta model's main entry point.

        Users call this as if talking to one model. Internally we select
        a provider, call it, and retry on failure with a different provider.

        Supports filtering by model_type and model_scale when model is "meta-model".
        """
        user_prompt = request.get_user_prompt()
        sys_prompt = request.get_system_prompt()
        temperature = request.temperature
        max_tokens = request.max_tokens
        response_format = request.response_format
        stream = request.stream

        self.logger.info(f"chat() — user_prompt: {user_prompt[:80]}...")

        # Case 1: Specific Routing (provider/model format)
        if "/" in request.model and request.model != "meta-model":
            try:
                provider_name, model_name = request.model.split("/", 1)
                self.logger.info(
                    f"Specific routing requested: {provider_name} ({model_name})"
                )

                start_time = time.time()
                model_resp = await self.call_provider_api(
                    provider_name=provider_name,
                    model_name=model_name,
                    user_prompt=user_prompt,
                    system_prompt=sys_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    stream=stream,
                )
                latency_ms = (time.time() - start_time) * 1000

                if stream:
                    return model_resp  # It's an AsyncGenerator

                if self.usage_tracker:
                    self.usage_tracker.record_usage(
                        provider_name,
                        model_name,
                        self.selector.estimate_tokens(user_prompt),
                        self.selector.estimate_tokens(model_resp),
                    )

                return build_response(
                    content=model_resp,
                    provider=provider_name,
                    model=model_name,
                    latency_ms=latency_ms,
                    attempt=1,
                )
            except Exception as e:
                self.logger.error(f"Specific routing to {request.model} failed: {e}")
                return build_error_response(
                    error_message=f"Specific routing to {request.model} failed: {str(e)}",
                    attempt=1,
                )

        # Case 2: Meta Model Routing (Default) - with optional type/scale filter
        max_retries = settings.MAX_RETRIES
        attempt = 0
        exclude_providers: list[str] = []
        last_error = ""

        while attempt < max_retries:
            try:
                provider_name, model_name, wait_time = self.selector.select(
                    user_prompt,
                    sys_prompt,
                    exclude_providers=exclude_providers.copy(),
                    model_type=request.model_type,
                    model_scale=request.model_scale,
                )

                if wait_time > 0:
                    if wait_time > settings.MAX_QUOTA_WAIT:
                        self.logger.warning(
                            f"Wait time {wait_time:.1f}s exceeds MAX_QUOTA_WAIT. Failing."
                        )
                        return build_error_response(
                            error_message=f"All models are at capacity. Wait time {wait_time:.1f}s exceeds limit.",
                            attempt=attempt + 1,
                        )

                    self.logger.info(
                        f"All models busy. Waiting {wait_time:.1f}s before retry..."
                    )
                    await asyncio.sleep(wait_time)
                    continue

                self.logger.info(
                    f"Attempt {attempt + 1}: Selected {provider_name} ({model_name})"
                )

                start_time = time.time()
                model_resp = await self.call_provider_api(
                    provider_name=provider_name,
                    model_name=model_name,
                    user_prompt=user_prompt,
                    system_prompt=sys_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                )
                latency_ms = (time.time() - start_time) * 1000

                if stream:
                    return model_resp  # It's an AsyncGenerator

                if self.usage_tracker:
                    self.usage_tracker.record_usage(
                        provider_name,
                        model_name,
                        self.selector.estimate_tokens(user_prompt),
                        self.selector.estimate_tokens(model_resp),
                    )

                return build_response(
                    content=model_resp,
                    provider=provider_name,
                    model=model_name,
                    latency_ms=latency_ms,
                    attempt=attempt + 1,
                )

            except AuthenticationError as e:
                self.logger.error(f"Auth failure for {e.provider}: {e}")
                attempt += 1
                last_error = str(e)
                if "provider_name" in locals():
                    exclude_providers.append(provider_name)

            except (ProviderError, RateLimitError) as e:
                attempt += 1
                last_error = str(e)
                self.logger.warning(f"Attempt {attempt} failed: {last_error}")

                if "provider_name" in locals() and "model_name" in locals():
                    cooldown = 60 if isinstance(e, RateLimitError) else 30
                    self.selector.trigger_circuit_breaker(
                        provider_name, model_name, cooldown
                    )
                    exclude_providers.append(provider_name)

            except Exception as e:
                attempt += 1
                last_error = str(e)
                self.logger.warning(f"Attempt {attempt} unexpected error: {last_error}")
                if "provider_name" in locals():
                    exclude_providers.append(provider_name)

            if attempt >= max_retries:
                self.logger.error(
                    f"All {max_retries} attempts failed. Last error: {last_error}"
                )
                return build_error_response(
                    error_message=f"All retries failed. Last error: {last_error}",
                    attempt=attempt,
                )

        return build_error_response(
            error_message="Unexpected retry loop exit",
            attempt=attempt,
        )

    # ── Provider call ───────────────────────────────────────────────

    async def call_provider_api(
        self,
        provider_name: str,
        model_name: str,
        user_prompt: str,
        system_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
        response_format: object = None,
        stream: bool = False,
    ) -> str | object:
        """Call a specific provider's model API."""
        self.logger.info(f"Calling {provider_name} model: {model_name} (stream={stream})")

        api_client = self.registry.get_client(provider_name)

        # Combine user system prompt with standard prompt
        full_sys_prompt = f"{system_prompt}\n\n{settings.STANDARD_SYSTEM_PROMPT}"

        # Inject response format hint if requested
        if response_format and getattr(response_format, "type", None) == "json_object":
            json_hint = (
                "\n\nIMPORTANT: Return ONLY a valid JSON object. "
                "Do not include markdown blocks or any other text."
            )
            full_sys_prompt += json_hint

        model_resp = await api_client.call_model_api(
            user_prompt=user_prompt,
            model=model_name,
            sys_instruct=full_sys_prompt,
            temperature=temperature or settings.DEFAULT_TEMPERATURE,
            max_tokens=max_tokens or settings.DEFAULT_MAX_TOKENS,
            stream=stream,
        )

        if not stream:
            self.logger.debug(f"Model response:\n{model_resp}")
        return model_resp

    # ── Model discovery ─────────────────────────────────────────────

    async def list_all_provider_models(self) -> dict[str, list[str]]:
        """Discover models from all registered providers in parallel."""
        self.logger.info("Discovering models from all providers...")
        discovered = {}

        clients = self.registry.all_clients()
        tasks = {
            name: asyncio.create_task(client.list_models())
            for name, client in clients.items()
        }

        for name, task in tasks.items():
            try:
                discovered[name] = await task
            except Exception as e:
                self.logger.error(f"Failed to list models for {name}: {e}")
                discovered[name] = []

        return discovered
