"""Thin async clients for upstream LLM providers.

Provider is auto-selected: model names starting with "claude" go to
Anthropic, everything else goes to any OpenAI-compatible endpoint
(OpenAI, Azure OpenAI, vLLM, Ollama, internal gateways...).
"""
from __future__ import annotations

import time
import uuid

import httpx

from .config import Settings


class LLMProxy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))

    def _provider_for(self, model: str) -> str:
        if self.settings.llm_provider != "auto":
            return self.settings.llm_provider
        return "anthropic" if model.lower().startswith("claude") else "openai"

    async def chat_completion(
        self, model: str, messages: list[dict], temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[dict, int, int]:
        """Returns (response_dict, prompt_tokens, completion_tokens)."""
        provider = self._provider_for(model)
        if provider == "anthropic":
            return await self._anthropic(model, messages, temperature, max_tokens)
        return await self._openai_compatible(model, messages, temperature, max_tokens)

    async def _openai_compatible(self, model, messages, temperature, max_tokens):
        url = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        resp = await self.client.post(
            url,
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        return data, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)

    async def _anthropic(self, model, messages, temperature, max_tokens):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        conversation = [
            {"role": "assistant" if m["role"] == "assistant" else "user",
             "content": m["content"]}
            for m in messages if m["role"] in ("user", "assistant")
        ]
        resp = await self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "system": system or None,
                "messages": conversation,
                "max_tokens": max_tokens or 1024,
                "temperature": temperature if temperature is not None else 1.0,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage", {})
        pt, ct = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        openai_shape = {
            "id": data.get("id", f"chatcmpl-{uuid.uuid4().hex}"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": data.get("stop_reason", "stop"),
            }],
            "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
        }
        return openai_shape, pt, ct