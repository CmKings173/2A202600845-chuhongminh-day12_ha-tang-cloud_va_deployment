"""
Rate Limiter — Sliding Window Counter

Giới hạn số request theo từng API key trong 1 phút.
Algorithm: sliding window — chính xác hơn fixed window.

Limitation: in-memory → không chia sẻ giữa multiple instances.
Production cần Redis-backed rate limiter (e.g. slowapi + Redis).
"""
import time
from collections import defaultdict, deque
from fastapi import HTTPException

from app.config import settings


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter.

    Mỗi key (API key, user_id, IP...) có một deque chứa timestamps
    của các request trong window. Khi request mới đến:
      1. Loại bỏ timestamps cũ (ngoài window)
      2. Kiểm tra nếu số lượng >= limit → 429
      3. Append timestamp mới vào deque
    """

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> dict:
        """
        Kiểm tra rate limit cho key.
        Raise HTTP 429 nếu vượt quá.
        Returns: dict với limit info để gắn vào response headers.
        """
        now = time.time()
        window = self._buckets[key]
        cutoff = now - self.window_seconds

        # Xóa timestamps cũ ra khỏi sliding window
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= self.max_requests:
            # Tính thời gian phải chờ đến khi oldest request ra khỏi window
            retry_after = int(window[0] + self.window_seconds - now) + 1
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": self.max_requests,
                    "window_seconds": self.window_seconds,
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(window[0] + self.window_seconds)),
                    "Retry-After": str(retry_after),
                },
            )

        # Ghi nhận request này
        window.append(now)
        remaining = self.max_requests - len(window)

        return {
            "limit": self.max_requests,
            "remaining": remaining,
            "reset_at": int(now) + self.window_seconds,
        }

    def get_stats(self, key: str) -> dict:
        """Trả về stats hiện tại (không check, không block)."""
        now = time.time()
        window = self._buckets[key]
        active = sum(1 for t in window if t >= now - self.window_seconds)
        return {
            "requests_in_window": active,
            "limit": self.max_requests,
            "remaining": max(0, self.max_requests - active),
        }


# Singleton — dùng chung trong toàn app
rate_limiter = SlidingWindowRateLimiter(
    max_requests=settings.rate_limit_per_minute,
    window_seconds=60,
)
