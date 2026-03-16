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

    def select_within(self, num_of_tokens: int, strategy: str = "roundrobin") -> tuple[ApiLimitsTracker | None, float]:
        """Try to route request within this provider. Returns (model, wait_time)."""
        if strategy == "random":
            return self.select_within_random(num_of_tokens)
        elif strategy == "roundrobin":
            return self.select_within_roundrobin(num_of_tokens)
        else:
            return self.select_within_roundrobin(num_of_tokens)

    def select_within_random(self, num_of_tokens: int) -> tuple[ApiLimitsTracker | None, float]:
        """Try to route request within this provider using random selection."""
        indices = list(range(len(self.models)))
        random.shuffle(indices)
        
        wait_times = []
        for idx in indices:
            model = self.models[idx]
            if model.can_handle(num_of_tokens):
                model.record_usage(num_of_tokens)
                self.last_used_index = idx
                self.usage_counter[model.model_name] = self.usage_counter.get(model.model_name, 0) + 1
                return model, 0.0
            wait_times.append(model.get_wait_time(num_of_tokens))
            
        return None, min(wait_times) if wait_times else float('inf')

    def select_within_roundrobin(self, num_of_tokens: int) -> tuple[ApiLimitsTracker | None, float]:
        """Try to route request within this provider using round-robin selection."""
        num_models = len(self.models)
        if num_models == 0: return None, float('inf')

        start_index = (self.last_used_index + 1) % num_models
        wait_times = []

        for i in range(num_models):
            curr_index = (start_index + i) % num_models
            curr_model = self.models[curr_index]
            
            if curr_model.can_handle(num_of_tokens):
                curr_model.record_usage(num_of_tokens)
                self.last_used_index = curr_index
                self.usage_counter[curr_model.model_name] = self.usage_counter.get(curr_model.model_name, 0) + 1
                return curr_model, 0.0
            
            wait_times.append(curr_model.get_wait_time(num_of_tokens))
            
        return None, min(wait_times) if wait_times else float('inf')

    def __repr__(self) -> str:
        return f"<Provider {self.name}>"
