from __future__ import annotations

from hashlib import md5
import json
import logging
import math
import time
from typing import Any

from core.config import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()

_redis_client: Any | None = None


def get_redis_client() -> Any:
    global _redis_client

    if _redis_client is None:
        from redis.asyncio import from_url

        _redis_client = from_url(settings.redis_url, decode_responses=True)
    return _redis_client


class LeakyBucketRateLimiter:
    def __init__(self, key: str, capacity: int, leak_rate: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        if leak_rate <= 0:
            raise ValueError("leak_rate must be greater than zero")

        self.key = key
        self.capacity = capacity
        self.leak_rate = leak_rate
        self.ttl_seconds = max(3600, math.ceil((capacity / leak_rate) * 120))

    async def is_allowed(self) -> tuple[bool, float]:
        client = get_redis_client()

        while True:
            try:
                async with client.pipeline() as pipe:
                    now = time.time()
                    await pipe.watch(self.key)
                    state = await pipe.hgetall(self.key)

                    level = self._to_float(state.get("level"), default=0.0)
                    last_leak_time = self._to_float(
                        state.get("last_leak_time"),
                        default=now,
                    )

                    elapsed_minutes = max(0.0, (now - last_leak_time) / 60.0)
                    leaked_amount = elapsed_minutes * self.leak_rate
                    level = max(0.0, level - leaked_amount)

                    pipe.multi()
                    if level >= self.capacity:
                        wait_seconds = ((level - self.capacity) + 1) / self.leak_rate
                        wait_seconds *= 60.0
                        pipe.hset(
                            self.key,
                            mapping={
                                "level": level,
                                "last_leak_time": now,
                            },
                        )
                        pipe.expire(self.key, self.ttl_seconds)
                        await pipe.execute()
                        return False, max(0.0, wait_seconds)

                    pipe.hset(
                        self.key,
                        mapping={
                            "level": level + 1.0,
                            "last_leak_time": now,
                        },
                    )
                    pipe.expire(self.key, self.ttl_seconds)
                    await pipe.execute()
                    return True, 0.0
            except Exception as exc:
                from redis.exceptions import WatchError

                if isinstance(exc, WatchError):
                    continue
                raise

    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


async def cache_get(key: str) -> Any | None:
    client = get_redis_client()
    raw_value = await client.get(key)
    if raw_value is None:
        return None

    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        logger.warning("Invalid cached JSON for key %s", key)
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    client = get_redis_client()
    await client.set(key, json.dumps(value, default=str), ex=ttl_seconds)


def make_cache_key(*args: Any) -> str:
    joined = ":".join(str(arg) for arg in args)
    digest = md5(joined.encode("utf-8")).hexdigest()
    return f"cache:{digest}"


async def acquire_lock(job_id: str, ttl_seconds: int) -> bool:
    client = get_redis_client()
    result = await client.set(f"lock:job:{job_id}", "1", nx=True, ex=ttl_seconds)
    return bool(result)


async def release_lock(job_id: str) -> None:
    client = get_redis_client()
    await client.delete(f"lock:job:{job_id}")


application_limiter = LeakyBucketRateLimiter(
    "rate_limit:applications",
    settings.rate_limit_capacity,
    settings.rate_limit_leak_rate,
)


__all__ = [
    "LeakyBucketRateLimiter",
    "acquire_lock",
    "application_limiter",
    "cache_get",
    "cache_set",
    "get_redis_client",
    "make_cache_key",
    "release_lock",
]
