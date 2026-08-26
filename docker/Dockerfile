# ---- Stage 1: dependencies ----
FROM python:3.11-slim AS deps
ENV PIP_NO_CACHE_DIR=1
WORKDIR /build

# Presidio needs spaCy's English model at runtime
RUN pip install "spacy>=3.7,<4" && python -m spacy download en_core_web_lg

COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- Stage 2: runtime ---- 
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY app ./app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"] 