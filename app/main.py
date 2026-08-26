"""LLM Security Gateway - FastAPI entrypoint.

Pipeline: authenticate -> rate limit -> semantic cache -> PII/PHI scrub
-> injection detection -> upstream LLM call -> response scrub -> audit
log -> cache store.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, Header, HTTPException

from .audit.logger import AuditLogger
from .cache.semantic_cache import SemanticCache
from .config import get_settings
from .models import ChatRequest
from .proxy import LLMProxy
from .rate_limit.limiter import RateLimiter
from .security.injection import InjectionDetector
from .security.pii import PIIScrubber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


class LocalRateLimiter:
    """Permissive fallback used when Redis is unavailable in local development."""

    async def allow(self, key: str) -> tuple[bool, int]:
        return True, 0


class LocalSemanticCache:
    """No-op cache fallback; avoids treating a missing Redis server as fatal."""

    async def lookup(self, prompt: str) -> dict | None:
        return None

    async def store(self, prompt: str, response: dict) -> None:
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = None
    try:
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis.ping()
        app.state.redis = redis
    except Exception:  # noqa: BLE001
        logger.warning("Redis is unavailable; rate limiting and caching are disabled")
    app.state.llm = LLMProxy(settings)
    app.state.pii = PIIScrubber(settings.languages)
    app.state.injection = InjectionDetector(settings)
    try:
        app.state.audit = AuditLogger(settings.database_url)
    except Exception:  # noqa: BLE001
        if settings.environment != "development":
            raise
        logger.warning("Configured database is unavailable; using local SQLite audit log")
        app.state.audit = AuditLogger("sqlite:///./gateway.db")
    if app.state.redis is None:
        app.state.rate = LocalRateLimiter()
        app.state.cache = LocalSemanticCache()
    else:
        app.state.rate = RateLimiter(
            app.state.redis, settings.rate_limit_requests, settings.rate_limit_window_seconds
        )
        app.state.cache = SemanticCache(
            app.state.redis,
            threshold=settings.semantic_cache_threshold,
            ttl=settings.semantic_cache_ttl,
            max_entries=settings.semantic_cache_max_entries,
        )
    logger.info("Gateway ready")
    yield
    await app.state.llm.client.aclose()
    if app.state.redis is not None:
        await app.state.redis.aclose()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)


@app.get("/")
async def root():
    """Small landing response so opening the service URL does not return 404."""
    return {
        "service": settings.app_name,
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


def _authorize(x_api_key: str | None) -> None:
    if not x_api_key or x_api_key not in settings.api_keys:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


async def _audit(**kwargs) -> None:
    try:
        await asyncio.to_thread(app.state.audit.log, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to write audit log")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@app.post("/v1/chat/completions")
async def chat_completion(
    req: ChatRequest,
    x_api_key: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
    x_gw_user_id: str | None = Header(default=None),
    x_gw_app_id: str | None = Header(default=None),
):
    _authorize(x_api_key)
    request_id = x_request_id or uuid.uuid4().hex
    user_id = x_gw_user_id or "anonymous"
    app_id = x_gw_app_id or "default"
    start = time.perf_counter()

    def base_audit(**overrides) -> dict:
        kwargs = dict(
            request_id=request_id, user_id=user_id, app_id=app_id,
            endpoint="/v1/chat/completions", model=req.model,
            prompt_redacted=None, response_redacted=None,
            prompt_tokens=0, completion_tokens=0,
            latency_ms=int((time.perf_counter() - start) * 1000),
            injection_score=0.0, injection_blocked=False,
            pii_entities={}, decision="allowed", cache_hit=False,
        )
        kwargs.update(overrides)
        return kwargs

    if req.stream:
        raise HTTPException(status_code=501, detail="Streaming is not supported yet")

    # 1) Rate limiting (sliding window, per user+app)
    allowed, current = await app.state.rate.allow(f"{user_id}:{app_id}")
    if not allowed:
        await _audit(**base_audit(decision="blocked_rate_limit"))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({current}/{settings.rate_limit_requests})",
        )

    # 2) Semantic cache lookup
    cache_text = "\n".join(f"{m.role}:{m.content}" for m in req.messages)
    if settings.semantic_cache_enabled:
        cached = await app.state.cache.lookup(cache_text)
        if cached is not None:
            await _audit(**base_audit(decision="cache_hit", cache_hit=True))
            return cached

    # 3) PII / PHI redaction (Presidio) - scrub each user/system message
    scrubbed_messages: list[dict] = []
    total_pii: dict[str, int] = {}
    for m in req.messages:
        content = m.content
        if settings.redact_pii and m.role in ("user", "system"):
            content, counts = await asyncio.to_thread(app.state.pii.scrub, content)
            for entity, n in counts.items():
                total_pii[entity] = total_pii.get(entity, 0) + n
        scrubbed_messages.append({"role": m.role, "content": content})

    # 4) Prompt-injection detection on all user messages
    injection_score, matched_rules = 0.0, []
    if settings.block_injection:
        for m in req.messages:
            if m.role != "user":
                continue
            score, rules = await asyncio.to_thread(app.state.injection.detect, m.content)
            injection_score = max(injection_score, score)
            matched_rules.extend(rules)
        if injection_score >= settings.injection_threshold:
            await _audit(**base_audit(
                prompt_redacted="\n".join(msg["content"] for msg in scrubbed_messages),
                injection_score=injection_score,
                injection_blocked=True,
                decision="blocked_injection",
            ))
            logger.warning(
                "request_id=%s injection blocked score=%.2f rules=%s",
                request_id, injection_score, matched_rules,
            )
            raise HTTPException(status_code=403, detail="Prompt injection detected")

    # 5) Call the upstream LLM
    try:
        response_data, pt, ct = await app.state.llm.chat_completion(
            req.model, scrubbed_messages, req.temperature, req.max_tokens
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream LLM error: {exc.response.status_code}")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Could not reach upstream LLM provider")

    # 6) Redact PII in the model's response (optional)
    if settings.redact_response_pii:
        try:
            raw = response_data["choices"][0]["message"]["content"]
            cleaned, resp_pii = await asyncio.to_thread(app.state.pii.scrub, raw)
            response_data["choices"][0]["message"]["content"] = cleaned
            for entity, n in resp_pii.items():
                total_pii[entity] = total_pii.get(entity, 0) + n
        except (KeyError, IndexError):
            pass

    # 7) Cache the response
    if settings.semantic_cache_enabled:
        await app.state.cache.store(cache_text, response_data)

    # 8) Audit log (PostgreSQL)
    await _audit(**base_audit(
        prompt_redacted="\n".join(msg["content"] for msg in scrubbed_messages),
        response_redacted=(
            response_data["choices"][0]["message"]["content"]
            if response_data.get("choices") else None
        ),
        prompt_tokens=pt,
        completion_tokens=ct,
        injection_score=injection_score,
        pii_entities=total_pii,
    ))

    return response_data

@app.get("/admin/audit")
async def audit_logs(limit: int = 50, x_api_key: str | None = Header(default=None)):
    """View recent audit entries (admin only)."""
    _authorize(x_api_key)
    return await asyncio.to_thread(app.state.audit.recent, limit)


@app.get("/admin/policy")
async def policy(x_api_key: str | None = Header(default=None)):
    """Inspect active security policy (admin only)."""
    _authorize(x_api_key)
    return {
        "block_injection": settings.block_injection,
        "injection_threshold": settings.injection_threshold,
        "redact_pii": settings.redact_pii,
        "redact_response_pii": settings.redact_response_pii,
        "rate_limit": {
            "requests": settings.rate_limit_requests,
            "window_seconds": settings.rate_limit_window_seconds,
        },
        "semantic_cache": {
            "enabled": settings.semantic_cache_enabled,
            "threshold": settings.semantic_cache_threshold,
            "ttl": settings.semantic_cache_ttl,
        },
    }
