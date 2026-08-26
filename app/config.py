"""Central configuration. Every setting can be overridden via env vars
prefixed with GW_ (e.g. GW_OPENAI_API_KEY)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LLM Security Gateway"
    environment: str = "development"

    # --- Gateway authentication ---
    gateway_api_keys: str = "dev-key-change-me"  # comma-separated

    # --- Upstream LLM provider ---
    llm_provider: str = "auto"          # auto | openai | anthropic
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # --- Infrastructure ---
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql://gateway:gateway@localhost:5432/gateway"

    # --- Security policies ---
    block_injection: bool = True
    injection_threshold: float = 0.7    # 0..1, above = block request
    redact_pii: bool = True
    redact_response_pii: bool = True
    pii_languages: str = "en"           # comma-separated

    # --- Rate limiting ---
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # --- Semantic cache ---
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.92  # cosine similarity to count as hit
    semantic_cache_ttl: int = 3600
    semantic_cache_max_entries: int = 500

    # --- Optional Rebuff injection layer ---
    rebuff_enabled: bool = False
    openai_api_key_for_rebuff: str = ""
    openai_model_for_rebuff: str = "gpt-3.5-turbo"
    pinecone_api_key: str = ""
    pinecone_environment: str = ""
    pinecone_index_name: str = "rebuff"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GW_", extra="ignore")

    @property
    def api_keys(self) -> list[str]:
        return [k.strip() for k in self.gateway_api_keys.split(",") if k.strip()]

    @property
    def languages(self) -> list[str]:
        return [lang.strip() for lang in self.pii_languages.split(",") if lang.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()