"""Sliding-window rate limiter backed by Redis sorted sets."""
from __future__ import annotations

import time
import uuid

import redis.asyncio as aioredis


class RateLimiter:
    def __init__(self, redis: aioredis.Redis, limit: int, window: int) -> None:
        self.redis = redis
        self.limit = limit
        self.window = window

    async def allow(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, current_count_in_window)."""
        now = time.time()
        rkey = f"ratelimit:{key}"
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(rkey, 0, now - self.window)  # drop expired
        pipe.zadd(rkey, {f"{now}:{uuid.uuid4().hex}": now})
        pipe.zcard(rkey)
        pipe.expire(rkey, self.window)
        _, _, count, _ = await pipe.execute()
        return count <= self.limit, count