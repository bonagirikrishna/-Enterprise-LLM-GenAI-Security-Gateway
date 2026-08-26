from datetime import datetime
from pydantic import BaseModel, Field


class GatewayRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    user_id: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="general", max_length=128)


class GatewayResponse(BaseModel):
    request_id: str
    response: str
    redactions: int
    cached: bool
    policy_version: str = "2026.1"


class AuditItem(BaseModel):
    request_id: str
    user_id: str
    purpose: str
    decision: str
    redactions: int
    cache_hit: bool
    created_at: datetime


class MetricsResponse(BaseModel):
    total_requests: int
    allowed_requests: int
    blocked_requests: int
    redacted_requests: int
    cache_hits: int
    compliance_rate: float

