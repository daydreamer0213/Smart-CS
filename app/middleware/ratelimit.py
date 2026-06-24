"""In-memory token-bucket rate limiter per tenant.

Rate check happens BEFORE the request is processed so that
rate-limited requests never waste backend resources.
"""

import time
import threading

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiter:
    def __init__(self, rpm: int = 30):
        self._rpm = rpm
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()
        self._check_count = 0

    def check(self, key: str) -> tuple[bool, int]:
        """Thread-safe token bucket check. Returns (allowed, remaining).

        Periodically evicts stale buckets (those with tokens at full capacity
        and not accessed for > 5 minutes) to prevent unbounded memory growth.
        """
        now = time.monotonic()
        with self._lock:
            # Evict stale entries every 1000 checks
            self._check_count += 1
            if self._check_count % 1000 == 0:
                stale = [
                    k for k, (t, tok) in self._buckets.items()
                    if tok == self._rpm and now - t > 300
                ]
                for k in stale:
                    del self._buckets[k]

            last_refill, tokens = self._buckets.get(key, (now, self._rpm))
            elapsed = now - last_refill
            tokens = min(self._rpm, tokens + int(elapsed * self._rpm / 60))
            if tokens > 0:
                self._buckets[key] = (now, tokens - 1)
                return True, tokens - 1
            self._buckets[key] = (last_refill, tokens)
            return False, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rpm: int = 30):
        super().__init__(app)
        self._limiter = RateLimiter(rpm)

    async def dispatch(self, request, call_next):
        slug = getattr(request.state, "tenant", None)
        if slug is None:
            return await call_next(request)

        key = slug.slug if hasattr(slug, "slug") else str(slug)
        allowed, remaining = self._limiter.check(key)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "RATE_LIMITED", "message": "Too many requests"}},
                headers={
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": "60",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
