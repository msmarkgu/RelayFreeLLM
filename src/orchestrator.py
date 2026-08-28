"""
Agent Orchestrator — Map–Reduce multi-model task execution.

Decomposes a task via a planner LLM, fans out subtasks across models
in parallel, and synthesises the results into a single answer.
"""

import asyncio
import json
import re
import time

from .config import settings
from .logging_util import ProjectLogger
from .model_dispatcher import ModelDispatcher
from .model_selector import ModelSelector
from .models import (
    AgentRunRequest,
    AgentRunResponse,
    AgentSubtaskResult,
    AgentMetaInfo,
)


class AgentOrchestrator:
    """Map–Reduce orchestrator for multi-model task execution."""

    def __init__(self, dispatcher: ModelDispatcher, selector: ModelSelector):
        self.dispatcher = dispatcher
        self.selector = selector
        self.logger = ProjectLogger.get_logger(__name__)

    # ── Public entry point ────────────────────────────────────────────

    async def run(self, request: AgentRunRequest) -> AgentRunResponse:
        """Execute the full map–reduce pipeline and return a combined answer."""
        start = time.time()
        num_experts = min(request.num_experts, settings.AGENTS_MAX_PARALLEL_ABSOLUTE)

        # 1. Plan: decompose the task
        plan = await self._plan(request.task, request.use_case, num_experts)

        # 2. Select models for each expert subtask
        expert_specs = await self._select_experts(
            plan, request.task, request.use_case
        )

        # 3. Execute all expert subtasks in parallel
        expert_results, completed, failed = await self._execute_experts(
            expert_specs, request.use_case, request.max_tokens_per_subtask
        )

        # 4. Synthesise results
        final_answer, synth_provider, synth_model = await self._synthesize(
            request.task, request.use_case, expert_results,
            request.max_tokens_synthesis,
        )

        latency_ms = (time.time() - start) * 1000

        return AgentRunResponse(
            task=request.task,
            subtasks=expert_results,
            final_answer=final_answer,
            meta=AgentMetaInfo(
                planner_provider=getattr(self, "_last_planner_provider", None),
                planner_model=getattr(self, "_last_planner_model", None),
                synthesizer_provider=synth_provider,
                synthesizer_model=synth_model,
                latency_ms=round(latency_ms, 2),
                subtasks_completed=completed,
                subtasks_failed=failed,
            ),
        )

    # ── 1. Planner ────────────────────────────────────────────────────

    async def _plan(
        self, task: str, use_case: str, num_experts: int
    ) -> list[dict]:
        """Use a planner LLM to decompose *task* into subtasks."""
        planner_prompt = (
            f"{settings.AGENTS_PLANNER_PROMPT}\n\n"
            f"Number of subtasks: {num_experts}\n\n"
            f"User task:\n{task}"
        )

        planner_system = settings.AGENTS_EXPERT_PROMPTS.get(use_case, "")
        planner_system = f"{planner_system}\n\n{settings.AGENTS_PLANNER_PROMPT}"

        try:
            response_text = await self._call_model(
                planner_system,
                planner_prompt,
                model_type=settings.AGENTS_PLANNER_MODEL_TYPE,
                model_scale=settings.AGENTS_PLANNER_MODEL_SCALE,
                max_tokens=2000,
            )
        except Exception as e:
            self.logger.warning(f"Planner call failed ({e}); falling back to single-subtask.")
            return [self._single_subtask_fallback(task)]

        plan = self._parse_plan(response_text)
        if not plan:
            self.logger.warning("Could not parse planner output; falling back to single-subtask.")
            return [self._single_subtask_fallback(task)]
        return plan

    @staticmethod
    def _parse_plan(text: str) -> list[dict] | None:
        """Try to parse a JSON array of subtask specs from planner output."""
        text = text.strip()
        # Try direct JSON parse
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "subtasks" in data:
                return data["subtasks"]
        except json.JSONDecodeError:
            pass
        # Try to extract the first JSON array from the text
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _single_subtask_fallback(task: str) -> dict:
        """Return a single subtask when decomposition fails."""
        return {
            "id": 1,
            "description": "Full task (no decomposition)",
            "prompt": task,
            "model_type": None,
            "model_scale": None,
        }

    # ── 2. Expert selection ───────────────────────────────────────────

    async def _select_experts(
        self, plan: list[dict], task: str, use_case: str
    ) -> list[dict]:
        """Select one model per planned subtask, preferring distinct providers."""
        num = len(plan)
        tokens_est = (
            self.selector.estimate_tokens(task)
            + self.selector.estimate_tokens(settings.AGENTS_PLANNER_PROMPT)
        )

        # Determine the pool of available (provider, model) pairs.
        # We pass a rough user_input token estimate; the actual text
        # isn't critical — we mainly want to know which providers/models
        # have quota.
        available = self.selector.select_many(
            num=num,
            user_input=task,
            system_prompt=settings.AGENTS_PLANNER_PROMPT,
            model_type=None,
            model_scale=None,
        )

        specs: list[dict] = []
        for i, subtask in enumerate(plan):
            prov, model = available[i] if i < len(available) else (None, None)
            specs.append({
                "provider": prov,
                "model": model,
                "subtask": subtask,
            })
            if prov is None:
                self.logger.warning(
                    f"Subtask {subtask.get('id')}: no provider available; "
                    "will fail at execution time."
                )
        return specs

    # ── 3. Parallel expert execution ──────────────────────────────────

    async def _execute_experts(
        self,
        specs: list[dict],
        use_case: str,
        max_tokens: int,
    ) -> tuple[list[AgentSubtaskResult], int, int]:
        """Run all expert subtasks concurrently; return (results, completed, failed)."""
        expert_prompt_prefix = settings.AGENTS_EXPERT_PROMPTS.get(use_case, "")

        async def _run_one(spec: dict) -> AgentSubtaskResult | None:
            subtask = spec["subtask"]
            provider = spec["provider"]
            model = spec["model"]
            subtask_id = subtask.get("id", 0)
            description = subtask.get("description", "")
            subtask_prompt = subtask.get("prompt", "")

            if provider is None or model is None:
                self.logger.warning(f"Subtask {subtask_id}: no provider/model — skipping.")
                return None

            full_prompt = (
                f"{expert_prompt_prefix}\n\n"
                if expert_prompt_prefix
                else ""
            ) + subtask_prompt

            try:
                result_text = await self._call_model(
                    system_prompt=expert_prompt_prefix,
                    user_prompt=full_prompt,
                    provider_name=provider,
                    model_name=model,
                    max_tokens=max_tokens,
                )
                self.logger.info(
                    f"Subtask {subtask_id} completed via {provider}/{model}"
                )
                return AgentSubtaskResult(
                    id=subtask_id,
                    description=description,
                    provider=provider,
                    model=model,
                    result=result_text,
                )
            except Exception as e:
                self.logger.error(
                    f"Subtask {subtask_id} failed on {provider}/{model}: {e}"
                )
                # Retry once on another provider
                try:
                    alt_specs = self.selector.select_many(
                        num=1,
                        user_input=subtask_prompt,
                        system_prompt=expert_prompt_prefix,
                        exclude_providers=[provider],
                    )
                    if alt_specs:
                        alt_prov, alt_model = alt_specs[0]
                        result_text = await self._call_model(
                            system_prompt=expert_prompt_prefix,
                            user_prompt=full_prompt,
                            provider_name=alt_prov,
                            model_name=alt_model,
                            max_tokens=max_tokens,
                        )
                        self.logger.info(
                            f"Subtask {subtask_id} succeeded on retry: "
                            f"{alt_prov}/{alt_model}"
                        )
                        return AgentSubtaskResult(
                            id=subtask_id,
                            description=description,
                            provider=alt_prov,
                            model=alt_model,
                            result=result_text,
                        )
                except Exception as retry_err:
                    self.logger.error(
                        f"Subtask {subtask_id} retry also failed: {retry_err}"
                    )
                if not settings.AGENTS_CONTINUE_ON_SUBTASK_ERROR:
                    raise
                return None

        tasks = [_run_one(spec) for spec in specs]
        results_raw = await asyncio.gather(*tasks, return_exceptions=False)

        results: list[AgentSubtaskResult] = []
        completed = 0
        failed = 0
        for r in results_raw:
            if r is None:
                failed += 1
            elif isinstance(r, AgentSubtaskResult):
                results.append(r)
                completed += 1

        return results, completed, failed

    # ── 4. Synthesiser ────────────────────────────────────────────────

    async def _synthesize(
        self,
        task: str,
        use_case: str,
        expert_results: list[AgentSubtaskResult],
        max_tokens: int,
    ) -> tuple[str, str | None, str | None]:
        """Combine expert results into a final coherent answer."""
        if not expert_results:
            return "All expert subtasks failed. No answer could be synthesised.", None, None

        synthesizer_prefix = settings.AGENTS_SYNTHESIZER_PROMPT
        use_case_prefix = settings.AGENTS_EXPERT_PROMPTS.get(use_case, "")

        # Build numbered expert results
        expert_sections = []
        for i, er in enumerate(expert_results, 1):
            expert_sections.append(
                f"--- Expert {i} ({er.description}) [{er.provider}/{er.model}] ---\n"
                f"{er.result}"
            )
        combined_experts = "\n\n".join(expert_sections)

        # Truncate combined experts to fit within a reasonable context budget.
        # Conservative: cap at ~4000 words (~5200 tokens) for the synthesis input.
        max_combined_words = 4000
        combined_words = combined_experts.split()
        if len(combined_words) > max_combined_words:
            combined_experts = " ".join(combined_words[:max_combined_words]) + "\n[...truncated...]"

        synthesis_prompt = (
            f"{synthesizer_prefix}\n\n"
            f"Original task: {task}\n\n"
            f"{combined_experts}"
        )

        response_text = await self._call_model(
            system_prompt=f"{use_case_prefix}\n\n{synthesizer_prefix}" if use_case_prefix else synthesizer_prefix,
            user_prompt=synthesis_prompt,
            model_type=settings.AGENTS_SYNTHESIZER_MODEL_TYPE,
            model_scale=settings.AGENTS_SYNTHESIZER_MODEL_SCALE,
            max_tokens=max_tokens,
        )

        # Determine which provider/model was used for synthesis
        synth_provider = getattr(self, "_last_call_provider", None)
        synth_model = getattr(self, "_last_call_model", None)

        return response_text, synth_provider, synth_model

    # ── Low-level model call ──────────────────────────────────────────

    async def _call_model(
        self,
        system_prompt: str,
        user_prompt: str,
        provider_name: str | None = None,
        model_name: str | None = None,
        model_type: str | None = None,
        model_scale: str | None = None,
        max_tokens: int = 4000,
    ) -> str:
        """
        Make a single LLM call via the dispatcher's provider layer.

        When *provider_name* and *model_name* are given, calls that
        specific provider directly.  Otherwise uses the selector to
        choose one based on *model_type* / *model_scale*.
        """
        if provider_name and model_name:
            result = await self.dispatcher.call_provider_api(
                provider_name=provider_name,
                model_name=model_name,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=max_tokens,
                stream=False,
                client_messages=None,
            )
            self._last_call_provider = provider_name
            self._last_call_model = model_name
            return result

        # Select a provider/model, then call it.
        # If a type/scale filter is specified but no model matches,
        # fall back to any available model (no filter).
        try:
            prov, model, _wait = self.selector.select(
                user_input=user_prompt,
                system_prompt=system_prompt,
                model_type=model_type,
                model_scale=model_scale,
            )
        except RuntimeError:
            if model_type or model_scale:
                self.logger.info(
                    f"No {model_type or ''}/{model_scale or ''} model available; "
                    "falling back to any available model."
                )
                prov, model, _wait = self.selector.select(
                    user_input=user_prompt,
                    system_prompt=system_prompt,
                )
            else:
                raise

        result = await self.dispatcher.call_provider_api(
            provider_name=prov,
            model_name=model,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=max_tokens,
            stream=False,
            client_messages=None,
        )
        self._last_call_provider = prov
        self._last_call_model = model
        return result
