import asyncio
import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from tender_compliance_api.extraction.adapter import LlmCallConfig
from tender_compliance_api.extraction.openai_adapter import (
    OpenAiLlmAdapter,
    _adapt_unsupported_option,
    _azure_foundry_base_url,
    _completion_options,
)


def _config(model: str, *, max_tokens: int | None, temperature: float | None) -> LlmCallConfig:
    return LlmCallConfig(
        provider="openai",
        model=model,
        prompt_version="test",
        schema_version="test",
        call_site="test",
        max_tokens=max_tokens,
        temperature=temperature,
    )


def test_initial_options_preserve_existing_contract_for_all_deployments() -> None:
    assert _completion_options(_config("gpt-5.4-nano", max_tokens=1200, temperature=0)) == {
        "max_tokens": 1200,
        "temperature": 0,
    }


def test_other_models_keep_legacy_completion_options() -> None:
    assert _completion_options(_config("gpt-4o", max_tokens=1200, temperature=0)) == {
        "max_tokens": 1200,
        "temperature": 0,
    }


def test_omitted_completion_limits_stay_omitted() -> None:
    assert _completion_options(_config("gpt-5.4-nano", max_tokens=None, temperature=None)) == {}


def test_bare_azure_foundry_endpoint_uses_models_route() -> None:
    assert _azure_foundry_base_url("https://example.openai.azure.com/") == (
        "https://example.openai.azure.com/models/",
        True,
    )


def test_explicit_openai_compatible_endpoint_is_preserved() -> None:
    endpoint = "https://example.openai.azure.com/openai/v1"
    assert _azure_foundry_base_url(endpoint) == (endpoint, False)


def test_non_azure_base_url_is_preserved() -> None:
    endpoint = "https://api.example.com/v1"
    assert _azure_foundry_base_url(endpoint) == (endpoint, False)


def test_bare_azure_endpoint_configures_route_version_and_api_key_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))
    OpenAiLlmAdapter(
        model="deployment-alias",
        base_url="https://example.openai.azure.com/",
        api_key="test-key",
    )._client()

    assert captured == {
        "api_key": "test-key",
        "base_url": "https://example.openai.azure.com/models/",
        "default_headers": {"api-key": "test-key"},
        "default_query": {"api-version": "2024-05-01-preview"},
    }


def test_unsupported_max_tokens_adapts_to_completion_tokens() -> None:
    class ProviderError(Exception):
        status_code = 400
        code = "unsupported_parameter"
        param = "max_tokens"

    options: dict[str, object] = {"max_tokens": 1200, "temperature": 0}
    assert _adapt_unsupported_option(ProviderError(), options)
    assert options == {"max_completion_tokens": 1200, "temperature": 0}


def test_unsupported_temperature_uses_model_default() -> None:
    class ProviderError(Exception):
        status_code = 400
        code = "unsupported_value"
        param = "temperature"

    options: dict[str, object] = {"max_completion_tokens": 1200, "temperature": 0}
    assert _adapt_unsupported_option(ProviderError(), options)
    assert options == {"max_completion_tokens": 1200}


def test_unrelated_provider_error_does_not_change_request_options() -> None:
    class ProviderError(Exception):
        status_code = 401
        code = "authentication_error"
        param = None

    options: dict[str, object] = {"max_tokens": 1200, "temperature": 0}
    assert not _adapt_unsupported_option(ProviderError(), options)
    assert options == {"max_tokens": 1200, "temperature": 0}


def test_image_call_retries_only_with_provider_rejected_options_removed() -> None:
    class Probe(BaseModel):
        result: str

    class UnsupportedParameter(Exception):
        status_code = 400

        def __init__(self, param: str, code: str) -> None:
            self.param = param
            self.code = code

    class Completions:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        async def parse(self, **kwargs: object) -> SimpleNamespace:
            self.requests.append(kwargs)
            if len(self.requests) == 1:
                raise UnsupportedParameter("max_tokens", "unsupported_parameter")
            if len(self.requests) == 2:
                raise UnsupportedParameter("temperature", "unsupported_value")
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(parsed=Probe(result="exact")),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            )

    completions = Completions()
    adapter = OpenAiLlmAdapter(model="deployment-alias", api_key="test-key")
    adapter._client = lambda: SimpleNamespace(  # type: ignore[method-assign]
        chat=SimpleNamespace(completions=completions)
    )
    config = _config("deployment-alias", max_tokens=1200, temperature=0)

    result = asyncio.run(
        adapter.extract_with_image(
            system_prompt="static instructions",
            user_text="synthetic prompt",
            image_bytes=b"synthetic image",
            image_mime_type="image/png",
            response_model=Probe,
            config=config,
        )
    )

    assert result.response == Probe(result="exact")
    assert [
        {
            k: request[k]
            for k in ("max_tokens", "max_completion_tokens", "temperature")
            if k in request
        }
        for request in completions.requests
    ] == [
        {"max_tokens": 1200, "temperature": 0},
        {"max_completion_tokens": 1200, "temperature": 0},
        {"max_completion_tokens": 1200},
    ]
