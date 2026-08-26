import hashlib
import json
from uuid import uuid4
import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import Settings
from app.models import AuditEvent
from app.security import detect_injection, redact_pii


class GatewayService:
    def __init__(self, settings: Settings, redis: Redis | None):
        self.settings, self.redis = settings, redis

    async def enforce_rate_limit(self, user_id: str) -> None:
        if not self.redis:
            return
        key = f"rate:{user_id}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 60)
        if count > self.settings.rate_limit_per_minute:
            raise ValueError("Rate limit exceeded. Try again in one minute.")

    async def ask_provider(self, prompt: str) -> str:
        if self.settings.llm_provider == "demo":
            return "Demo provider received your security-screened request: " + prompt[:500]
        if self.settings.llm_provider != "openai" or not self.settings.openai_api_key:
            raise RuntimeError("LLM provider is not configured")
        payload = {"model": self.settings.openai_model, "messages": [{"role": "user", "content": prompt}]}
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            result = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
            result.raise_for_status()
        return result.json()["choices"][0]["message"]["content"]

    async def process(self, *, prompt: str, user_id: str, purpose: str, session: AsyncSession) -> dict:
        request_id = str(uuid4())
        injection = detect_injection(prompt)
        if injection:
            await self._audit(session, request_id, user_id, purpose, "blocked", "", "", [injection], 0, False)
            raise PermissionError(injection)
        await self.enforce_rate_limit(user_id)
        sanitized, findings = redact_pii(prompt)
        cache_key = "prompt:" + hashlib.sha256(sanitized.encode()).hexdigest()
        cached = False
        response = None
        if self.redis:
            response = await self.redis.get(cache_key)
            cached = response is not None
        if not response:
            response = await self.ask_provider(sanitized)
            if self.redis:
                await self.redis.setex(cache_key, 300, response)
        decision = "redacted" if findings else "allowed"
        await self._audit(session, request_id, user_id, purpose, decision, sanitized, response, findings, len(findings), cached)
        return {"request_id": request_id, "response": response, "redactions": len(findings), "cached": cached}

    async def _audit(self, session, request_id, user_id, purpose, decision, prompt, response, findings, redactions, cached):
        session.add(AuditEvent(request_id=request_id, user_id=user_id, purpose=purpose, decision=decision,
            sanitized_prompt=prompt, response_preview=response[:1000], findings=json.dumps(findings), redactions=redactions, cache_hit=cached))
        await session.commit()
