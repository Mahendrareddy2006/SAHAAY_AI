"""
Sahaay AI - In-Memory Rate Limiting & Abuse Protection
(src/sahaay/security/rate_limiter.py)

Zero-dependency, thread-safe sliding-window rate limiter for public and sensitive endpoints.
Protects against automated volumetric scraping, denial of service, and brute-force token inspection.
"""

from collections import defaultdict, deque
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Dict, Optional, Tuple
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """
    Thread-safe sliding-window in-memory rate limiter.
    Maintains rolling timestamps per client key with automated window cleanup.
    """

    def __init__(self, default_limit_per_minute: int = 60):
        self.default_limit_per_minute = default_limit_per_minute
        self._lock = threading.Lock()
        self._requests: Dict[str, deque] = defaultdict(deque)
        self._enabled: bool = True

    def set_enabled(self, enabled: bool) -> None:
        """Enables or disables rate limiting (useful for isolated unit testing)."""
        with self._lock:
            self._enabled = enabled

    def check_rate_limit(
        self,
        key: str,
        limit_per_minute: Optional[int] = None,
        window_seconds: float = 60.0,
    ) -> Tuple[bool, int, float]:
        """
        Evaluates whether a request for `key` exceeds the rate limit.
        Returns: (is_allowed, remaining_requests, retry_after_seconds)
        """
        if not self._enabled:
            return True, 999, 0.0

        limit = limit_per_minute if limit_per_minute is not None else self.default_limit_per_minute
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            client_queue = self._requests[key]

            # Evict timestamps outside the sliding window
            while client_queue and client_queue[0] <= window_start:
                client_queue.popleft()

            current_count = len(client_queue)
            if current_count >= limit:
                oldest_timestamp = client_queue[0]
                retry_after = max(1.0, round(window_seconds - (now - oldest_timestamp), 1))
                return False, 0, retry_after

            # Record this valid request timestamp
            client_queue.append(now)
            remaining = max(0, limit - len(client_queue))
            return True, remaining, 0.0

    def reset(self) -> None:
        """Clears all tracked client timestamps."""
        with self._lock:
            self._requests.clear()


# Global singleton rate limiter instance
default_rate_limiter = SlidingWindowRateLimiter(default_limit_per_minute=60)


def enforce_rate_limit(
    request: Request,
    limit_per_minute: int = 60,
    client_key_prefix: str = "ip",
) -> None:
    """
    FastAPI dependency / helper enforcing sliding-window rate limit on endpoints.
    Raises HTTPException(429) if limit is exceeded.
    """
    client_ip = getattr(request.client, "host", "127.0.0.1") if request.client else "127.0.0.1"
    key = f"{client_key_prefix}:{client_ip}"

    is_allowed, remaining, retry_after = default_rate_limiter.check_rate_limit(
        key=key,
        limit_per_minute=limit_per_minute,
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too Many Requests: Rate limit of {limit_per_minute} requests/min exceeded. "
                f"Please back off. Retry after {retry_after} seconds."
            ),
            headers={"Retry-After": str(int(retry_after))},
        )
