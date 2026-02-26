from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.config import settings


class RateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self.max_per_minute = max_per_minute
        self._requests = defaultdict(deque)

    def check(self, user_id: int) -> None:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=1)
        queue = self._requests[user_id]
        while queue and queue[0] < window_start:
            queue.popleft()
        if len(queue) >= self.max_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
        queue.append(now)


rate_limiter = RateLimiter(settings.rate_limit_per_minute)
