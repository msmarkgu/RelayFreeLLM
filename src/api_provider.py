import json
import os
import random
import time
from collections import deque

from .api_limits_tracker import ApiLimitsTracker

CUR_DIR = os.path.dirname(os.path.realpath(__file__))


class ApiProvider:
    def __init__(self, name: str, models: list[ApiLimitsTracker]) -> None:
        self.name = name
        self.models = models  # list of ModelAPIs
        self.last_used_index = -1  # for round-robin selection
        self.usage_counter = {}

    def select_within(
        self,
        num_of_tokens: int,
        strategy: str = "roundrobin",
        model_type: str | None = None,
        model_scale: str | None = None,
        model_name: str | None = None,
    ) -> tuple[ApiLimitsTracker | None, float]:
        """
        Try to route request within this provider.

        Args:
            num_of_tokens: Estimated token count for the request
            strategy: Selection strategy ("random" or "roundrobin")
            model_type: Filter by model type (text, coding, image, speech, etc.)
            model_scale: Filter by model scale (large, medium, small)
            model_name: Filter by substring of model name

        Returns:
            Tuple of (model, wait_time)
        """
        filtered_models = self.models
        if model_type:
            filtered_models = [m for m in filtered_models if m.model_type == model_type]
        if model_scale:
            filtered_models = [
                m for m in filtered_models if m.model_scale == model_scale
            ]
        if model_name:
            filtered_models = [
                m
                for m in filtered_models
                if model_name.lower() in m.model_name.lower()
            ]

        if not filtered_models:
            return None, float("inf")

        if strategy == "random":
            return self._select_from_list_random(filtered_models, num_of_tokens)
        else:
            return self._select_from_list_roundrobin(filtered_models, num_of_tokens)

    def _select_from_list_random(
        self, models: list[ApiLimitsTracker], num_of_tokens: int
    ) -> tuple[ApiLimitsTracker | None, float]:
        """Try to route request using random selection from given model list."""
        indices = list(range(len(models)))
        random.shuffle(indices)

        wait_times = []
        for idx in indices:
            model = models[idx]
            if model.can_handle(num_of_tokens):
                model.record_usage(num_of_tokens)
                self.last_used_index = self.models.index(model)
                self.usage_counter[model.model_name] = (
                    self.usage_counter.get(model.model_name, 0) + 1
                )
                return model, 0.0
            wait_times.append(model.get_wait_time(num_of_tokens))

        return None, min(wait_times) if wait_times else float("inf")

    def _select_from_list_roundrobin(
        self, models: list[ApiLimitsTracker], num_of_tokens: int
    ) -> tuple[ApiLimitsTracker | None, float]:
        """Try to route request using round-robin selection from given model list."""
        num_models = len(models)
        if num_models == 0:
            return None, float("inf")

        start_index = 0
        if self.last_used_index >= 0:
            for i, m in enumerate(models):
                if self.models.index(m) > self.last_used_index:
                    start_index = i
                    break

        wait_times = []

        for i in range(num_models):
            curr_index = (start_index + i) % num_models
            curr_model = models[curr_index]

            if curr_model.can_handle(num_of_tokens):
                curr_model.record_usage(num_of_tokens)
                self.last_used_index = self.models.index(curr_model)
                self.usage_counter[curr_model.model_name] = (
                    self.usage_counter.get(curr_model.model_name, 0) + 1
                )
                return curr_model, 0.0

            wait_times.append(curr_model.get_wait_time(num_of_tokens))

        return None, min(wait_times) if wait_times else float("inf")

    def __repr__(self) -> str:
        return f"<Provider {self.name}>"
