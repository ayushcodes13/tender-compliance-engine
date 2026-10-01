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

    # Processing limits
    max_retries: int = 5
    max_concurrency: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
