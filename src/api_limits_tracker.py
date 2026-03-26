import json
import os
import random
import time
from collections import deque

CUR_DIR = os.path.dirname(os.path.realpath(__file__))


class ApiLimitsTracker:
    def __init__(
        self,
        provider_name: str,
        model_name: str,
        limits: dict,
        model_type: str = "text",
        model_scale: str = "medium",
    ) -> None:
        self.prvdr_name = provider_name
        self.model_name = model_name
        self.limits = limits
        self.model_type = model_type
        self.model_scale = model_scale
        self.cooldown_until = 0

        # Usage tracking
        self.deque_req_sec = deque()  # usually 1 request per second
        self.deque_req_min = deque()
        self.deque_req_hr = deque()
        self.deque_req_day = deque()

        self.deque_tok_min = deque()
        self.deque_tok_hr = deque()
        self.deque_tok_day = deque()

        # Running totals (avoid recomputing sums every check)
        self.total_tok_min = 0
        self.total_tok_hr = 0
        self.total_tok_day = 0

    def cleanup(self) -> None:
        """Remove expired timestamps from usage trackers."""
        now = time.time()

        # requests cleanup
        while self.deque_req_sec and now - self.deque_req_sec[0] > 1:
            self.deque_req_sec.popleft()  # Removes and returns an element from the left end of the deque.

        while self.deque_req_min and now - self.deque_req_min[0] > 60:
            self.deque_req_min.popleft()
        while self.deque_req_hr and now - self.deque_req_hr[0] > 3600:
            self.deque_req_hr.popleft()
        while self.deque_req_day and now - self.deque_req_day[0] > 86400:
            self.deque_req_day.popleft()

        # tokens cleanup (also update running totals)
        while self.deque_tok_min and now - self.deque_tok_min[0][0] > 60:
            _, t = self.deque_tok_min.popleft()
            self.total_tok_min -= t
        while self.deque_tok_hr and now - self.deque_tok_hr[0][0] > 3600:
            _, t = self.deque_tok_hr.popleft()
            self.total_tok_hr -= t
        while self.deque_tok_day and now - self.deque_tok_day[0][0] > 86400:
            _, t = self.deque_tok_day.popleft()
            self.total_tok_day -= t

    def can_handle(self, num_of_tokens: int) -> bool:
        """Check if model can handle a request of `tokens` now."""
        # Check cooldown first
        if time.time() < self.cooldown_until:
            return False

        self.cleanup()
        L = self.limits

        rps_ok = (L["requests_per_second"] == -1) or (
            len(self.deque_req_sec) < L["requests_per_second"]
        )
        rpm_ok = (L["requests_per_minute"] == -1) or (
            len(self.deque_req_min) < L["requests_per_minute"]
        )
        rph_ok = (L["requests_per_hour"] == -1) or (
            len(self.deque_req_hr) < L["requests_per_hour"]
        )
        rpd_ok = (L["requests_per_day"] == -1) or (
            len(self.deque_req_day) < L["requests_per_day"]
        )

        tpm_ok = (L["tokens_per_minute"] == -1) or (
            self.total_tok_min + num_of_tokens <= L["tokens_per_minute"]
        )
        tph_ok = (L["tokens_per_hour"] == -1) or (
            self.total_tok_hr + num_of_tokens <= L["tokens_per_hour"]
        )
        tpd_ok = (L["tokens_per_day"] == -1) or (
            self.total_tok_day + num_of_tokens <= L["tokens_per_day"]
        )

        all_ok = (
            rps_ok and rpm_ok and rph_ok and rpd_ok and tpm_ok and tph_ok and tpd_ok
        )
        return all_ok

    def get_wait_time(self, num_of_tokens: int) -> float:
        """Calculate wait time in seconds until this model can handle the request."""
        now = time.time()
        wait_times = [0.0]

        if now < self.cooldown_until:
            wait_times.append(self.cooldown_until - now)

        self.cleanup()
        L = self.limits

        # Request limits
        if (
            L["requests_per_second"] != -1
            and len(self.deque_req_sec) >= L["requests_per_second"]
        ):
            wait_times.append(max(0, 1.0 - (now - self.deque_req_sec[0])))

        if (
            L["requests_per_minute"] != -1
            and len(self.deque_req_min) >= L["requests_per_minute"]
        ):
            wait_times.append(max(0, 60.0 - (now - self.deque_req_min[0])))

        if (
            L["requests_per_hour"] != -1
            and len(self.deque_req_hr) >= L["requests_per_hour"]
        ):
            wait_times.append(max(0, 3600.0 - (now - self.deque_req_hr[0])))

        if (
            L["requests_per_day"] != -1
            and len(self.deque_req_day) >= L["requests_per_day"]
        ):
            wait_times.append(max(0, 86400.0 - (now - self.deque_req_day[0])))

        # Token limits
        def calc_token_wait(deque_obj, limit_val, total_val, window_sec):
            if limit_val == -1:
                return 0.0
            if num_of_tokens > limit_val:
                return float("inf")

            # If we already exceed limit, find how long until enough tokens expire
            temp_total = total_val + num_of_tokens
            if temp_total <= limit_val:
                return 0.0

            needed = temp_total - limit_val
            wait = 0.0
            accumulated = 0
            for ts, count in deque_obj:
                accumulated += count
                wait = max(wait, window_sec - (now - ts))
                if accumulated >= needed:
                    break
            return wait

        wait_times.append(
            calc_token_wait(
                self.deque_tok_min, L["tokens_per_minute"], self.total_tok_min, 60
            )
        )
        wait_times.append(
            calc_token_wait(
                self.deque_tok_hr, L["tokens_per_hour"], self.total_tok_hr, 3600
            )
        )
        wait_times.append(
            calc_token_wait(
                self.deque_tok_day, L["tokens_per_day"], self.total_tok_day, 86400
            )
        )

        return max(wait_times)

    def trigger_cooldown(self, duration_sec: int = 300) -> None:
        """Put this model in cooldown for a specified duration."""
        self.cooldown_until = time.time() + duration_sec

    def record_usage(self, num_of_tokens: int) -> None:
        now = time.time()
        self.deque_req_sec.append(now)
        self.deque_req_min.append(now)
        self.deque_req_hr.append(now)
        self.deque_req_day.append(now)
        self.deque_tok_min.append((now, num_of_tokens))
        self.deque_tok_hr.append((now, num_of_tokens))
        self.deque_tok_day.append((now, num_of_tokens))
        
        self.total_tok_min += num_of_tokens
        self.total_tok_hr += num_of_tokens
        self.total_tok_day += num_of_tokens

    def __repr__(self) -> str:
        return f"<Provider {self.prvdr_name} Model {self.model_name}>"
