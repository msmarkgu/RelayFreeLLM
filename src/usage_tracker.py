"""
Usage Tracker — tracks global token consumption and request counts.
"""

import json
import os
import time
from threading import Lock

from .logging_util import ProjectLogger

class UsageTracker:
    def __init__(self, persistence_file: str = "usage_stats.json"):
        self.logger = ProjectLogger.get_logger(__name__)
        self.persistence_file = persistence_file
        self.lock = Lock()
        self.stats = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.persistence_file):
            try:
                with open(self.persistence_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to load usage stats: {e}")
        return {"providers": {}, "total": {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}}

    def _save(self):
        try:
            with open(self.persistence_file, "w") as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save usage stats: {e}")

    def record_usage(self, provider: str, model: str, prompt_tokens: int, completion_tokens: int):
        """Record usage for a specific call."""
        with self.lock:
            # Update Provider/Model stats
            if provider not in self.stats["providers"]:
                self.stats["providers"][provider] = {"models": {}, "prompt_tokens": 0, "completion_tokens": 0, "requests": 0}
            
            p_stats = self.stats["providers"][provider]
            if model not in p_stats["models"]:
                p_stats["models"][model] = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}
            
            m_stats = p_stats["models"][model]
            
            for target in [p_stats, m_stats, self.stats["total"]]:
                target["prompt_tokens"] += prompt_tokens
                target["completion_tokens"] += completion_tokens
                target["requests"] += 1
            
            self._save()

    def get_stats(self) -> dict:
        """Get current usage statistics."""
        with self.lock:
            return self.stats.copy()
