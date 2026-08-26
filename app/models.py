from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: Optional[str] = None


class ChatRequest(BaseModel):
    """OpenAI-compatible chat completion request body."""
    model: str = Field(..., examples=["gpt-4o-mini", "claude-3-5-sonnet-20241022"])
    messages: list[ChatMessage] = Field(..., min_length=1)
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1024
    top_p: Optional[float] = None
    stream: Optional[bool] = False