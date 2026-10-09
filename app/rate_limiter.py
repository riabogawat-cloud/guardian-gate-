"""Fixed-window rate limiter on Redis.

Per client, per window: allow N requests, then answer HTTP 429.
Known weakness: a client can burst N at the end of one window and N at the start of the
next (2N in a short time). A sliding window or token bucket fixes that.
"""
import logging

import redis
from fastapi import Depends, HTTPException, Request, Response

from app.cache import get_redis
from app.config import settings

log = logging.getLogger("guardiangate")


def client_id(request: Request) -> str:
    # API key if the client sends one, otherwise fall back to IP address
    return request.headers.get("x-api-key") or (request.client.host if request.client else "unknown")


def rate_limit(request: Request, response: Response, r: redis.Redis = Depends(get_redis)) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return

    key = f"rate:{client_id(request)}"
    try:
        # MULTI/EXEC pipeline = one atomic step:
        #  1) create the counter with expiry only if it doesn't exist yet
        #  2) increment it   3) read the remaining time to reset
        pipe = r.pipeline(transaction=True)
        pipe.set(key, 0, ex=settings.RATE_LIMIT_WINDOW, nx=True)
        pipe.incr(key)
        pipe.ttl(key)
        _, count, ttl = pipe.execute()
    except redis.RedisError:
        log.warning("Redis unavailable; rate limiter failing OPEN")  # fail-open on purpose
        return

    remaining = max(settings.RATE_LIMIT_REQUESTS - count, 0)
    response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(remaining)

    if count > settings.RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(max(ttl, 1))},
        )
