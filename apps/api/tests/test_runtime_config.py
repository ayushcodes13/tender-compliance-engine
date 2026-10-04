"""Production runtime configuration must fail closed instead of using fakes."""

import pytest

from tender_compliance_api.config import RuntimeConfigurationError, Settings


def _production_settings(**overrides: str) -> Settings:
    values = {
        "app_env": "production",
        "auth_mode": "single_workspace",
        "database_url": "postgresql+asyncpg://tce:secret@postgres/tce",
        "redis_url": "redis://redis:6379/0",
        "object_storage_local_path": "/app/object-storage",
        "openai_api_key": "test-key-not-real",
        "malware_scanner_mode": "clamav",
        "clamav_host": "clamav",
    }
    values.update(overrides)
    return Settings(**values)


def test_development_runtime_allows_local_fallbacks() -> None:
    settings = Settings(app_env="development")

    assert settings.production_configuration_errors() == []
    settings.validate_runtime_configuration()


def test_complete_private_pilot_runtime_is_valid() -> None:
    settings = _production_settings()

    assert settings.production_configuration_errors() == []
    settings.validate_runtime_configuration()


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("database_url", "DATABASE_URL is required"),
        ("redis_url", "REDIS_URL is required"),
        ("openai_api_key", "OPENAI_API_KEY is required"),
    ],
)
def test_production_requires_durable_dependencies(field: str, message: str) -> None:
    settings = _production_settings(**{field: ""})

    with pytest.raises(RuntimeConfigurationError, match=message):
        settings.validate_runtime_configuration()


def test_production_requires_durable_object_storage() -> None:
    settings = _production_settings(
        object_storage_local_path="",
        object_storage_endpoint="",
    )

    with pytest.raises(RuntimeConfigurationError, match="durable object storage"):
        settings.validate_runtime_configuration()


def test_production_rejects_development_header_auth() -> None:
    settings = _production_settings(auth_mode="development_headers")

    with pytest.raises(RuntimeConfigurationError, match="AUTH_MODE=single_workspace"):
        settings.validate_runtime_configuration()


def test_s3_endpoint_satisfies_durable_storage_requirement() -> None:
    settings = _production_settings(
        object_storage_local_path="",
        object_storage_endpoint="https://s3.example.test",
    )

    settings.validate_runtime_configuration()


def test_production_requires_real_malware_scanner() -> None:
    settings = _production_settings(malware_scanner_mode="fake")

    with pytest.raises(RuntimeConfigurationError, match="MALWARE_SCANNER_MODE=clamav"):
        settings.validate_runtime_configuration()


def test_production_requires_clamav_host() -> None:
    settings = _production_settings(clamav_host="")

    with pytest.raises(RuntimeConfigurationError, match="CLAMAV_HOST is required"):
        settings.validate_runtime_configuration()
