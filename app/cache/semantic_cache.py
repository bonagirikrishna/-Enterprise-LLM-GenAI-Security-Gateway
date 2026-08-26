"""Redis-backed semantic cache.

Similarity is computed over character n-gram vectors (cosine), so near-
duplicate prompts ("What is Q3 revenue?" vs "What was Q3 revenue?") share
a cached response while exact-match hashing alone would miss them.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter

import redis.asyncio as aioredis

_SPACE_RE = re.compile(r"\s+")


def _char_ngrams(text: str, n: int = 3) -> Counter:
    text = _SPACE_RE.sub(" ", text).lower().strip()
    if len(text) < n:
        return Counter([text])
    return Counter(text[i:i + n] for i in range(len(text) - n + 1))


def _cosine(a: Counter, b: Counter) -> float:
    intersection = sum((a & b).values())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return intersection / (na * nb)


class SemanticCache:
    INDEX_KEY = "semcache:index"

    def __init__(self, redis: aioredis.Redis, threshold: float = 0.92,
                 ttl: int = 3600, max_entries: int = 500) -> None:
        self.redis = redis
        self.threshold = threshold
        self.ttl = ttl
        self.max_entries = max_entries

    async def lookup(self, prompt: str) -> dict | None:
        vec = _char_ngrams(prompt)
        keys = await self.redis.lrange(self.INDEX_KEY, 0, -1)
        best_key, best_sim = None, self.threshold
        for key in keys:
            raw = await self.redis.get(key)
            if not raw:
                continue
            entry = json.loads(raw)
            sim = _cosine(vec, entry["vector"])
            if sim >= best_sim:
                best_key, best_sim = key, sim
        if best_key is None:
            return None
        return json.loads(await self.redis.get(best_key))["response"]

    async def store(self, prompt: str, response: dict) -> None:
        key = f"semcache:{hashlib.sha256(prompt.encode()).hexdigest()}"
        if await self.redis.exists(key):
            return
        entry = {
            "prompt": prompt,
            "vector": dict(_char_ngrams(prompt)),
            "response": response,
            "ts": time.time(),
        }
        await self.redis.set(key, json.dumps(entry), ex=self.ttl)
        await self.redis.rpush(self.INDEX_KEY, key)
        await self.redis.ltrim(self.INDEX_KEY, -self.max_entries, -1)