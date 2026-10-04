from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeConfigurationError(RuntimeError):
    """Raised when a production process would start with unsafe fallbacks."""


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")

    app_env: str = "development"
    app_name: str = "tender-compliance-engine"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = ""

    # Authentication. single_workspace is intentionally simple: it is for
    # a private pilot / one-customer deployment and automatically bootstraps
    # one owner membership. Public multi-user SaaS should use a real IdP.
    auth_mode: str = "development_headers"
    single_workspace_user_id: str = "00000000-0000-0000-0000-000000000001"
    single_workspace_org_id: str = "00000000-0000-0000-0000-000000000002"
    single_workspace_org_name: str = "Tender Compliance Workspace"

    # Browser/API boundary.
    cors_allowed_origins: str = "http://localhost:3000"

    # Object storage. A private single-host pilot uses a durable shared
    # filesystem volume; public/cloud deployments can configure S3 instead.
    object_storage_local_path: str = ""
    object_storage_endpoint: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    object_storage_bucket: str = "tender-documents"
    object_storage_region: str = "us-east-1"

    # Redis (queue/broker seam)
    redis_url: str = ""

    # OpenAI extraction/reasoning provider.
    # The API key is read from the environment; it is never logged or
    # committed. When empty, OpenAiLlmAdapter is still constructible (the
    # call fails fast at extraction time with a typed LlmCallError).
    # See docs/review.md for LLM extraction design notes.
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"

    # Processing limits
    max_retries: int = 5
    max_concurrency: int = 4

    # Resource limits
    upload_max_bytes: int = 50 * 1024 * 1024
    max_pdf_pages: int = 500
    request_timeout_seconds: float = 30.0

    # Retention policy (in days)
    retention_originals_days: int = 90
    retention_rendered_days: int = 30
    retention_exports_days: int = 30

    @property
    def is_production(self) -> bool:
        """Return whether this process is running the production runtime contract."""
        return self.app_env.strip().lower() == "production"

    def production_configuration_errors(self) -> list[str]:
        """Return missing/unsafe settings that would make production misleading.

        Development intentionally supports in-memory adapters and header identity
        for fast tests. Production does not: every user-visible upload must use a
        durable database, queue, and object store, and extraction must have a
        configured model credential.
        """
        if not self.is_production:
            return []

        errors: list[str] = []
        if not self.database_url.strip():
            errors.append("DATABASE_URL is required")
        if not self.redis_url.strip():
            errors.append("REDIS_URL is required")
        if not (
            self.object_storage_local_path.strip()
            or self.object_storage_endpoint.strip()
        ):
            errors.append(
                "durable object storage is required "
                "(OBJECT_STORAGE_LOCAL_PATH or OBJECT_STORAGE_ENDPOINT)"
            )
        if not self.openai_api_key.strip():
            errors.append("OPENAI_API_KEY is required")
        if self.auth_mode.strip() != "single_workspace":
            errors.append(
                "AUTH_MODE=single_workspace is required for the current private-pilot production mode"
            )
        return errors

    def validate_runtime_configuration(self) -> None:
        """Fail before serving traffic when the production runtime is incomplete."""
        errors = self.production_configuration_errors()
        if errors:
            raise RuntimeConfigurationError(
                "Production runtime configuration is incomplete: " + "; ".join(errors)
            )

    @property
    def cors_origins(self) -> list[str]:
        """Return normalized CORS origins from the comma-separated setting."""
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
