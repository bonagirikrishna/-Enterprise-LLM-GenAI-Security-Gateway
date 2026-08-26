"""The smallest useful FastAPI proxy for the OpenAI Chat Completions API.

Run with: uvicorn basic_proxy:app --reload
"""

import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="Basic LLM Proxy", version="0.1.0")


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)


class PromptResponse(BaseModel):
    response: str
    model: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/proxy", response_model=PromptResponse)
async def proxy(request: PromptRequest) -> PromptResponse:
    """Forward the prompt to OpenAI and return the assistant's text reply."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(500, "OPENAI_API_KEY is not set")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": request.prompt}],
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            upstream = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        upstream.raise_for_status()
        answer = upstream.json()["choices"][0]["message"]["content"]
        return PromptResponse(response=answer, model=model)
    except httpx.TimeoutException:
        raise HTTPException(504, "The LLM provider timed out")
    except httpx.HTTPStatusError as error:
        # Do not return an upstream response body: it can contain provider details.
        raise HTTPException(502, f"The LLM provider returned HTTP {error.response.status_code}")
    except (KeyError, IndexError, TypeError):
        raise HTTPException(502, "The LLM provider returned an unexpected response")

