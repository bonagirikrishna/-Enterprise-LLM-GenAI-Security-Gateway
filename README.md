# LLM & GenAI Security Gateway

A **secure proxy gateway** that sits between enterprise applications and LLM APIs (OpenAI, Anthropic, or internal models). It intercepts every prompt, redacts PII/PHI, blocks prompt injection attacks, applies rate limiting, caches semantically identical requests, and logs everything for compliance.

Corporate App / User ──▶ LLM Security Gateway ──▶ OpenAI / Anthropic / Internal LLM │ ├─ ✅ Authentication (X-API-Key) ├─ ⏱️ Rate Limiting (Redis) ├─ 🔍 Semantic Cache (Redis) ├─ 🛡️ PII/PHI Redaction (Microsoft Presidio) ├─ ⚠️ Prompt Injection Detection (Heuristics + Rebuff) └─ 📋 Audit Logging (PostgreSQL)

---

## Features

- **PII/PHI Redaction** — Detects and replaces names, emails, phone numbers, SSNs, credit cards, medical record numbers, health insurance IDs, ICD-10 codes, and more using Microsoft Presidio
- **Prompt Injection Protection** — Weighted regex heuristics detect DAN jailbreaks, system prompt extraction, role-play overrides, and encoded payloads. Optional Rebuff integration adds vector-DB similarity detection
- **Rate Limiting** — Sliding window per user+app (Redis sorted sets)
- **Semantic Caching** — Character n-gram cosine similarity reuses responses for near-identical prompts, reducing cost and latency
- **Full Audit Trail** — Every decision (allowed / blocked / cache hit) is logged to PostgreSQL with redacted payloads, token counts, injection scores, and PII entity counts
- **Provider Agnostic** — Routes `claude-*` models to Anthropic, everything else to any OpenAI-compatible endpoint (OpenAI, Azure, vLLM, Ollama, internal models)
- **Admin API** — View audit logs and active security policy at runtime

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | FastAPI + Uvicorn |
| PII/PHI Detection | Microsoft Presidio (spaCy `en_core_web_lg`) |
| Prompt Injection | Custom heuristics + Rebuff (optional) |
| Caching & Rate Limiting | Redis 7 |
| Audit Database | PostgreSQL 16 (SQLAlchemy ORM) |
| Deployment | Docker, Docker Compose, Kubernetes |

---

## Quick Start (Local Development)

### Prerequisites

- Python 3.11+
- Docker Desktop (for Redis + PostgreSQL)

### 1. Clone and set up

```bash
git clone https://github.com/yourusername/llm-security-gateway.git
cd llm-security-gateway

cp .env.example .env

Edit .env with your API keys:
GW_OPENAI_API_KEY=sk-your-openai-key

### 1. Clone and set 
