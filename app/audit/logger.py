"""PostgreSQL audit logging via SQLAlchemy (sync engine, called in threads)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, Integer,
                        String, Text, create_engine)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    request_id = Column(String(64), index=True)
    user_id = Column(String(128), index=True)
    app_id = Column(String(128), index=True)
    endpoint = Column(String(64))
    model = Column(String(128))
    prompt_redacted = Column(Text, nullable=True)
    response_redacted = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    injection_score = Column(Float, default=0.0)
    injection_blocked = Column(Boolean, default=False)
    pii_entities = Column(JSON, default=dict)
    decision = Column(String(32))  # allowed | blocked_injection | blocked_rate_limit | cache_hit
    cache_hit = Column(Boolean, default=False)


class AuditLogger:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True, pool_size=10)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)  # creates audit_log table if missing

    def log(self, **kwargs) -> None:
        with self.session_factory() as session:
            session.add(AuditLog(**kwargs))
            session.commit()

    def recent(self, limit: int = 50) -> list[dict]:
        with self.session_factory() as session:
            rows = (
                session.query(AuditLog)
                .order_by(AuditLog.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "request_id": r.request_id,
                    "user_id": r.user_id,
                    "app_id": r.app_id,
                    "model": r.model,
                    "decision": r.decision,
                    "cache_hit": r.cache_hit,
                    "injection_score": r.injection_score,
                    "injection_blocked": r.injection_blocked,
                    "pii_entities": r.pii_entities,
                    "prompt_redacted": r.prompt_redacted,
                    "latency_ms": r.latency_ms,
                }
                for r in rows
            ]