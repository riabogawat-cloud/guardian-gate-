"""Cache-aside helpers. If Redis is down we treat it as a cache miss (the app still works)."""
import json
import logging

import redis

from app.config import settings

log = logging.getLogger("guardiangate")

_client = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


LIST_PREFIX = "invoices:list:"


def invoice_key(invoice_id: int) -> str:
    return f"invoice:{invoice_id}"


def list_key(skip: int, limit: int) -> str:
    return f"{LIST_PREFIX}{skip}:{limit}"


def cache_get(r: redis.Redis, key: str):
    if not settings.CACHE_ENABLED:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except redis.RedisError:
        log.warning("Redis unavailable on cache_get; treating as miss")
        return None


def cache_set(r: redis.Redis, key: str, value) -> None:
    if not settings.CACHE_ENABLED:
        return
    try:
        r.set(key, json.dumps(value), ex=settings.CACHE_TTL)
    except redis.RedisError:
        log.warning("Redis unavailable on cache_set")


def invalidate_invoice(r: redis.Redis, invoice_id: int) -> None:
    """Called after update/delete so stale data is never served."""
    try:
        r.delete(invoice_key(invoice_id))
    except redis.RedisError:
        log.warning("Redis unavailable on invalidate_invoice")


def invalidate_lists(r: redis.Redis) -> None:
    """Any write can change list results, so drop every cached list page."""
    try:
        keys = list(r.scan_iter(match=LIST_PREFIX + "*"))
        if keys:
            r.delete(*keys)
    except redis.RedisError:
        log.warning("Redis unavailable on invalidate_lists")
