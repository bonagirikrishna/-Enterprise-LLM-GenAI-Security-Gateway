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


Edit `.env` with your API keys:

```env
GW_OPENAI_API_KEY=sk-your-openai-key
```

### 2. Start Redis and PostgreSQL

```bash
docker compose up -d postgres redis
```

### 3. Install dependencies and run

```bash
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
python -m spacy download en_core_web_lg

uvicorn app.main:app --reload --port 8000
```

### 4. Test it

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok","service":"LLM Security Gateway","environment":"development"}`

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"What is a firewall?"}]}'
```

---

## Docker Compose (Full Stack)

Run everything in containers — no local Python needed:

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

---

## Kubernetes Deployment

```bash
kubectl create namespace llm-gateway

kubectl create secret generic gateway-secrets -n llm-gateway \
  --from-literal=GW_OPENAI_API_KEY='sk-...' \
  --from-literal=GW_DATABASE_URL='postgresql://gateway:password@postgres:5432/gateway' \
  --from-literal=POSTGRES_PASSWORD='password'

kubectl apply -f k8s/
kubectl port-forward -n llm-gateway service/gateway 8000:80
```

See `k8s/` directory for full manifests including HPA, ingress, and StatefulSets.

---

## API Reference

### `GET /health`
Liveness check. No authentication required.

### `POST /v1/chat/completions`
OpenAI-compatible chat endpoint. All security layers applied.

**Headers:**
| Header | Required | Purpose |
|---|---|---|
| `X-API-Key` | Yes | Gateway authentication |
| `X-Request-Id` | No | Your trace ID (auto-generated if omitted) |
| `X-GW-User-Id` | No | End-user identity (for rate limiting + audit) |
| `X-GW-App-Id` | No | Application identity (for rate limiting + audit) |

**Request body** (OpenAI chat completion format):

```json
{
  "model": "gpt-4o-mini",
  "messages": [{"role": "user", "content": "Your prompt here"}],
  "temperature": 0.7,
  "max_tokens": 1024
}
```

### `GET /admin/audit?limit=50`
View recent audit log entries. Requires valid `X-API-Key`.

### `GET /admin/policy`
View active security policy. Requires valid `X-API-Key`.

---

## Python SDK Integration

Replace your OpenAI client configuration to route through the gateway:

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-gateway-api-key",
    base_url="http://localhost:8000/v1",
    default_headers={"X-GW-User-Id": "alice"}
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Explain Kubernetes."}]
)
print(response.choices[0].message.content)
```

---

## Configuration

All settings are environment variables prefixed with `GW_`:

| Variable | Default | Description |
|---|---|---|
| `GW_GATEWAY_API_KEYS` | `dev-key-change-me` | Comma-separated API keys for gateway auth |
| `GW_LLM_PROVIDER` | `auto` | `auto`, `openai`, or `anthropic` |
| `GW_OPENAI_API_KEY` | — | OpenAI API key |
| `GW_ANTHROPIC_API_KEY` | — | Anthropic API key |
| `GW_BLOCK_INJECTION` | `true` | Enable prompt injection detection |
| `GW_INJECTION_THRESHOLD` | `0.7` | Score 0–1 above which a prompt is blocked |
| `GW_REDACT_PII` | `true` | Enable PII/PHI redaction on prompts |
| `GW_REDACT_RESPONSE_PII` | `true` | Enable PII/PHI redaction on responses |
| `GW_RATE_LIMIT_REQUESTS` | `100` | Max requests per window |
| `GW_RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window duration |
| `GW_SEMANTIC_CACHE_ENABLED` | `true` | Enable semantic response caching |
| `GW_SEMANTIC_CACHE_THRESHOLD` | `0.92` | Cosine similarity for cache hit |
| `GW_REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `GW_DATABASE_URL` | `postgresql://gateway:gateway@localhost:5432/gateway` | PostgreSQL connection string |

Full list in [.env.example](.env.example).

---

## Security Layers Explained

### PII/PHI Redaction
Uses Microsoft Presidio with spaCy NLP + custom recognizers for medical records, health insurance IDs, and ICD-10 codes. Values are replaced with `<ENTITY_TYPE>` placeholders so no sensitive data reaches the LLM or audit log.

### Prompt Injection Detection
A weighted regex engine scores messages against known attack patterns:
- "Ignore all previous instructions" → blocked
- DAN / jailbreak attempts → blocked
- System prompt extraction → blocked
- Role-play overrides → blocked
- Base64/encoded payloads → blocked

Optional Rebuff integration adds vector-DB similarity matching.

### Rate Limiting
Sliding window per `user_id:app_id` using Redis sorted sets. Configured via `GW_RATE_LIMIT_*` variables.

### Semantic Cache
Character n-gram cosine similarity (configurable threshold, default 0.92). Near-duplicate prompts ("What is Q3 revenue?" vs "What was Q3 revenue?") share cached responses, reducing API costs and latency.

---

## Testing

```bash
pytest tests/ -v
```

---

## Project Structure

```
llm-security-gateway/
├── app/
│   ├── main.py                  # FastAPI entrypoint, request pipeline
│   ├── config.py                # Environment-driven settings
│   ├── models.py                # Pydantic request/response models
│   ├── proxy.py                 # OpenAI + Anthropic upstream clients
│   ├── audit/logger.py          # PostgreSQL audit logging
│   ├── cache/semantic_cache.py  # Redis semantic cache
│   ├── rate_limit/limiter.py    # Redis rate limiter
│   └── security/
│       ├── pii.py               # Presidio PII/PHI scrubber
│       └── injection.py         # Injection detector (heuristics + Rebuff)
├── tests/
│   ├── test_pii.py
│   └── test_injection.py
├── docker/
│   └── Dockerfile
├── k8s/                         # Kubernetes manifests
├── docker-compose.yml           # Docker Compose deployment
├── requirements.txt
└── .env.example
```

---

## Production Checklist

- [ ] Rotate all default API keys
- [ ] Terminate TLS at the Ingress / load balancer
- [ ] Use a secrets manager (Vault, AWS Secrets Manager)
- [ ] Add per-tenant API keys with rate limit tiers
- [ ] Enable streaming (`stream=true`) with token-level PII scrubbing
- [ ] Set up PostgreSQL backups (WAL archiving)
- [ ] Configure Redis persistence (AOF)
- [ ] Add monitoring + alerting on `blocked_injection` and `429` spikes
- [ ] Run `pip-audit` / `trivy` in CI for dependency vulnerabilities

---

## License

MIT
```

---

To add this to your GitHub repo:

1. Save the content above as `README.md` in your project root (`D:\gen AI Security Gateway\README.md`)
2. Commit and push to GitHub:

```bash
git add README.md
git commit -m "Add comprehensive README"
git push
```

Replace `` in the clone URL with your actual GitHub username. If you want me to add or change any sections (screenshots, badges, specific deployment instructions, etc.), let me know.

