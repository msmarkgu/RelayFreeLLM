"""
Model Dispatcher — the core of the meta model.

Handles provider selection, retry logic with fallback,
and produces OpenAI-compatible responses.
"""

import asyncio
import time
import traceback
from collections import defaultdict

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
    ChatMessage
)
from .model_selector import ModelSelector
from .provider_registry import ProviderRegistry
from .logging_util import ProjectLogger
from .response_normalizer import ResponseNormalizer
from .style_config import get_style_directive
from .context_manager import ContextManager
from .config import settings
from typing import List, Optional, Union
import asyncio


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
        self.normalizer = ResponseNormalizer()
        self.context_manager = ContextManager()

        self.session_affinity_map = {}
        self.affinity_lock = asyncio.Lock()
        self.provider_locks = defaultdict(asyncio.Lock)

    # ── Primary "meta model" entry point (OpenAI-compatible) ────────

    async def chat(
        self,
        request: ChatCompletionRequest,
        conversation_history: Optional[List[ChatMessage]] = None,
        session_id: str = "default",
        use_server_side_system_prompt: Optional[bool] = None,
    ) -> ChatCompletionResponse | object:
        """
        The meta model's main entry point.

        Users call this as if talking to one model. Internally we select
        a provider, call it, and retry on failure with a different provider.

        Supports filtering by model_type and model_scale when model is "meta-model".

        Args:
            request: The chat completion request
            conversation_history: Optional list of previous messages for context
            session_id: Client session identifier (from X-Session-ID header)
            use_server_side_system_prompt: Override for
                USE_SERVER_SIDE_SYSTEM_PROMPT. When True the server always
                injects its standard prompt + style_directive and ignores
                the client's system message. When False the client's
                messages array is forwarded verbatim. Default (None)
                falls back to the server-wide setting.
        """
        user_prompt = request.get_user_prompt()
        # Preserve the original content of the last user message
        # (may be a list with text + image_url parts for multimodal).
        last_user_msg = next(
            (msg for msg in reversed(request.messages) if msg.role == "user"),
            None,
        )
        user_content = last_user_msg.content if last_user_msg else user_prompt
        sys_prompt = request.get_system_prompt()
        temperature = request.temperature
        max_tokens = request.max_tokens
        response_format = request.response_format
        stream = request.stream

        response_format_dict = None
        if response_format:
            response_format_dict = (
                {"type": response_format.type}
                if hasattr(response_format, "type")
                else {}
            )

        self.logger.info(f"chat() — user_prompt: {user_prompt[:80]}...")

        # Resolve the flag: per-request override (if set) or server default.
        effective_use_ss = (
            use_server_side_system_prompt
            if use_server_side_system_prompt is not None
            else settings.USE_SERVER_SIDE_SYSTEM_PROMPT
        )
        client_messages = request.messages if not effective_use_ss else None

        # Case 1: Specific Routing (provider/model format)
        if "/" in request.model and request.model != "meta-model":
            try:
                raw_provider, model_name = request.model.split("/", 1)

                # Prefer user-specified provider; fall back to another if needed
                provider_name = raw_provider
                if raw_provider in self.selector.providers:
                    has_model = any(
                        m.model_name == model_name
                        for m in self.selector.providers[raw_provider].models
                    )
                    if has_model:
                        provider_name = raw_provider
                    else:
                        for prov_name, provider in self.selector.providers.items():
                            if prov_name == raw_provider:
                                continue
                            for model in provider.models:
                                if model.model_name == model_name:
                                    provider_name = prov_name
                                    self.logger.info(
                                        f"Corrected provider for '{model_name}': "
                                        f"'{raw_provider}' → '{prov_name}'"
                                    )
                                    break
                            if provider_name != raw_provider:
                                break

                self.logger.info(
                    f"Specific routing requested: {provider_name} ({model_name})"
                )

                start_time = time.time()
                model_resp = await self.call_provider_api(
                    provider_name=provider_name,
                    model_name=model_name,
                    user_prompt=user_content,
                    system_prompt=sys_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    stream=stream,
                    conversation_history=conversation_history,
                    session_id=session_id,
                    client_messages=client_messages,
                )
                latency_ms = (time.time() - start_time) * 1000

                if stream:
                    return self._stream_with_meta(model_resp, provider_name, model_name)

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
                self.logger.error(f"Specific routing to {request.model} failed: {e}\n{traceback.format_exc()}")
                return build_error_response(
                    error_message=f"Specific routing to {request.model} failed: {str(e)}",
                    attempt=1,
                )

        # Case 2: Meta Model Routing (Default) - with optional type/scale filter
        max_retries = settings.MAX_RETRIES
        attempt = 0
        exclude_providers: list[str] = []
        last_error = ""

        # Determine affinity
        preferred_provider = None
        affinity_model_name = request.model_name

        if settings.SESSION_AFFINITY_ENABLED and session_id != "default":
            async with self.affinity_lock:
                now = time.time()
                # Prune expired sessions
                expired = [sid for sid, data in self.session_affinity_map.items() if now - data["last_active"] > settings.SESSION_TTL_HOURS * 3600]
                for sid in expired:
                    del self.session_affinity_map[sid]

                # Safety net: limit map size to prevent unbounded growth
                max_sessions = settings.SESSION_MAX_SESSIONS
                if len(self.session_affinity_map) > max_sessions:
                    sorted_sessions = sorted(self.session_affinity_map.items(), key=lambda x: x[1]["last_active"])
                    sessions_to_remove = sorted_sessions[:len(self.session_affinity_map) - max_sessions + 100]
                    for sid, _ in sessions_to_remove:
                        del self.session_affinity_map[sid]
                    self.logger.info(f"Pruned {len(sessions_to_remove)} sessions due to size limit")

                # READ affinity (unconditionally, after pruning)
                if session_id in self.session_affinity_map:
                    data = self.session_affinity_map[session_id]
                    preferred_provider = data["provider"]
                    affinity_model_name = data["model"]
                    self.session_affinity_map[session_id]["last_active"] = now

        while attempt < max_retries:
            try:
                provider_name, model_name, wait_time = self.selector.select(
                    user_prompt,
                    sys_prompt,
                    preferred_provider=preferred_provider if attempt == 0 else None,
                    exclude_providers=exclude_providers.copy(),
                    model_type=request.model_type,
                    model_scale=request.model_scale,
                    model_name=affinity_model_name if (attempt == 0 and preferred_provider) else request.model_name,
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
                    user_prompt=user_content,
                    system_prompt=sys_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                    conversation_history=conversation_history,
                    session_id=session_id,
                    client_messages=client_messages,
                )
                latency_ms = (time.time() - start_time) * 1000

                if stream:
                    # Update Session Affinity on successful stream start
                    if settings.SESSION_AFFINITY_ENABLED and session_id != "default":
                        async with self.affinity_lock:
                            self.session_affinity_map[session_id] = {
                                "provider": provider_name,
                                "model": model_name,
                                "last_active": time.time()
                            }
                    return self._stream_with_meta(model_resp, provider_name, model_name)

                if self.usage_tracker:
                    self.usage_tracker.record_usage(
                        provider_name,
                        model_name,
                        self.selector.estimate_tokens(user_prompt),
                        self.selector.estimate_tokens(model_resp),
                    )

                # Update Session Affinity on success
                if settings.SESSION_AFFINITY_ENABLED and session_id != "default":
                    async with self.affinity_lock:
                        self.session_affinity_map[session_id] = {
                            "provider": provider_name,
                            "model": model_name,
                            "last_active": time.time()
                        }

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

    # ── Streaming metadata wrapper ───────────────────────────────

    async def _stream_with_meta(self, inner_gen, provider, model):
        """Wrap a streaming generator to emit metadata as the first item."""
        yield {"type": "meta", "provider": provider, "model": model}
        async for chunk in inner_gen:
            yield {"type": "content", "data": chunk}

    # ── Provider call ───────────────────────────────────────────────

    async def call_provider_api(
        self,
        provider_name: str,
        model_name: str,
        user_prompt: Union[str, list],
        system_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
        response_format: object = None,
        stream: bool = False,
        conversation_history: Optional[List[ChatMessage]] = None,
        session_id: str = "default",
        client_messages: Optional[List[ChatMessage]] = None,
    ) -> str | object:
        """
        Call a specific provider's model API.

        Args:
            provider_name: Name of the provider to call
            model_name: Name of the model to use
            user_prompt: Current user message
            system_prompt: System prompt
            temperature: Model temperature
            max_tokens: Max tokens to generate
            response_format: Response format (e.g., JSON)
            stream: Whether to stream the response
            conversation_history: Optional list of previous messages for
                context (used by the legacy reconstruction path)
            session_id: Client session identifier for context tracking
            client_messages: Optional full client message array. When
                provided (and USE_SERVER_SIDE_SYSTEM_PROMPT is False
                — per server default or per-request header), the
                dispatcher forwards the client's `messages` array
                directly to the provider in client order, skipping
                server-side system prompt injection and array
                reconstruction. Used by agent frameworks (LangChain,
                AutoGen, etc.) that manage their own conversation
                state.
        """
        self.logger.info(f"Calling {provider_name} model: {model_name} (stream={stream})")

        api_client = self.registry.get_client(provider_name)

        response_format_dict = None
        if response_format:
            response_format_dict = {"type": getattr(response_format, "type", None)}

        style_directive = get_style_directive(response_format_dict)
        base_sys_prompt = f"{system_prompt}\n\n{settings.STANDARD_SYSTEM_PROMPT}\n\n{style_directive}"

        # Verbatim path: forward the client's array as-is when
        # USE_SERVER_SIDE_SYSTEM_PROMPT is False (either from server
        # default or per-request header override). No server-side
        # system prompts are injected. The client's own system message
        # (if any) and array order are respected. Only a hard token-cap
        # trim is applied via the context manager.
        context_messages = []
        if client_messages is not None:
            target_context_tokens = self._calculate_target_context_tokens(
                provider_name, model_name, max_tokens
            )
            selected_history = self.context_manager.select_context_for_request(
                client_messages,
                session_id=session_id,
                target_context_tokens=target_context_tokens,
            )
            # Preserve original content (string or list w/ image_url parts)
            # for multimodal support; use get_text() only for the empty check.
            messages = [
                {"role": msg.role, "content": msg.content}
                for msg in selected_history
                if msg.get_text().strip()
            ]
            self.logger.debug(
                f"Verbatim path: forwarded {len(messages)} "
                f"of {len(client_messages)} client messages, "
                f"skipping server-side system prompt injection"
            )
        else:
            # Legacy reconstruction path: build [system, ...context, user]
            # from the extracted components.
            if conversation_history and len(conversation_history) > 0:
                # Calculate target context size based on provider/model limits
                target_context_tokens = self._calculate_target_context_tokens(
                    provider_name, model_name, max_tokens
                )

                # Use context manager to select appropriate portion of history
                selected_history = self.context_manager.select_context_for_request(
                    conversation_history,
                    session_id=session_id,
                    target_context_tokens=target_context_tokens
                )

                # Preserve original content for multimodal support; use
                # get_text() only for the empty check.
                context_messages = [
                    {"role": msg.role, "content": msg.content}
                    for msg in selected_history
                    if msg.get_text().strip()
                ]

                self.logger.debug(
                    f"Context management: selected {len(selected_history)} of "
                    f"{len(conversation_history)} messages for context"
                )

            # Build complete message list: [context] + [current user message]
            messages = []

            # Add system prompt if present
            if system_prompt:
                messages.append({"role": "system", "content": base_sys_prompt})

            # Add context messages
            messages.extend(context_messages)

            # Add current user message
            messages.append({"role": "user", "content": user_prompt})

        # Strip multimodal content parts for models that don't support vision.
        # Priority: 1) per-model modality from registry, 2) client-level fallback.
        model_modality = self._get_model_modality(provider_name, model_name)
        can_handle_images = model_modality == "vision" or (
            model_modality != "vision" and getattr(api_client, "supports_multimodal", False)
        )
        if not can_handle_images:
            normalized = []
            for msg in messages:
                content = msg["content"]
                if isinstance(content, list):
                    parts = [p["text"] for p in content if isinstance(p, dict) and p.get("type") == "text"]
                    content = " ".join(parts)
                normalized.append({"role": msg["role"], "content": content})
            messages = normalized

        # Global Provider Lock: Optional serialization per provider
        if settings.GLOBAL_PROVIDER_LOCK:
            self.logger.info(f"Global lock enabled. Waiting for {provider_name} lock...")
            async with self.provider_locks[provider_name]:
                model_resp = await api_client.call_model_api(
                    messages=messages,
                    model=model_name,
                    temperature=temperature or settings.DEFAULT_TEMPERATURE,
                    max_tokens=max_tokens or settings.DEFAULT_MAX_TOKENS,
                    stream=stream,
                )
        else:
            model_resp = await api_client.call_model_api(
                messages=messages,
                model=model_name,
                temperature=temperature or settings.DEFAULT_TEMPERATURE,
                max_tokens=max_tokens or settings.DEFAULT_MAX_TOKENS,
                stream=stream,
            )

        # Update usage tracking for context (for dynamic mode)
        if context_messages:
            def _extract_text(content):
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    return " ".join(
                        p["text"] for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                return str(content)
            context_tokens = self.selector.estimate_tokens(
                " ".join(_extract_text(m["content"]) for m in context_messages)
            )
            self.context_manager.update_usage(session_id, context_tokens)

        if not stream:
            normalized_resp = self.normalizer.normalize(model_resp, response_format_dict)
            self.logger.debug(f"Model response:\n{normalized_resp}")
            return normalized_resp
        return model_resp

    def _get_model_modality(self, provider_name: str, model_name: str) -> str:
        """Look up the modality for a specific provider/model from the registry."""
        providers = getattr(self.selector, "providers", None)
        if not isinstance(providers, dict):
            return "text"
        provider = providers.get(provider_name)
        if not provider:
            return "text"
        models = getattr(provider, "models", [])
        for model in models:
            if getattr(model, "model_name", None) == model_name:
                return getattr(model, "modality", "text")
        return "text"

    def _calculate_target_context_tokens(
        self,
        provider_name: str,
        model_name: str,
        max_tokens: Optional[int]
    ) -> int:
        """
        Calculate how many tokens we can use for context.

        Args:
            provider_name: Name of the provider
            model_name: Name of the model
            max_tokens: Max tokens reserved for response

        Returns:
            Maximum tokens available for context
        """
        max_context = 4096
        provider = self.selector.providers.get(provider_name)
        if provider:
            for model in provider.models:
                if model.model_name == model_name:
                    max_context = model.max_context_length
                    break


        # Reserve space for response and overhead
        response_reserve = settings.DEFAULT_MAX_TOKENS if max_tokens is None else max_tokens
        system_overhead = 500  # System prompts, style guides
        safety_margin = 100    # Extra buffer

        target_context = max(0, max_context - response_reserve - system_overhead - safety_margin)
        return target_context

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
