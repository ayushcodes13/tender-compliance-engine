from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")

    app_env: str = "development"
    app_name: str = "tender-compliance-engine"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = ""

    # Object storage (S3-compatible, e.g. MinIO locally)
    object_storage_endpoint: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    object_storage_bucket: str = "tender-documents"
    object_storage_region: str = "us-east-1"

    # Redis (queue/broker seam)
    redis_url: str = ""

    # LLM extraction (CP26) — OpenAI is the default provider (review.md).
    # The API key is read from the environment; it is never logged or
    # committed. When empty, OpenAiLlmAdapter is still constructible (the
    # call fails fast at extraction time with a typed LlmCallError).
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"

    # Processing limits
    max_retries: int = 5
    max_concurrency: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
