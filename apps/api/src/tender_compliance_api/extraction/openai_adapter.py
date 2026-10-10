"""OpenAI extraction adapter (CP26).

Production default per ``docs/review.md``: OpenAI ``gpt-4o`` with structured output
parsed directly into the :class:`ExtractionResponse` schema.  This adapter is
provider-agnostic only in that it implements the :class:`LlmAdapter` port — the
model/service never imports OpenAI directly.

The ``openai`` package is imported **lazily** (inside :meth:`_client`) so the
adapter — and therefore :func:`create_worker` — can be constructed without the
package installed.  A real call requires ``OPENAI_API_KEY`` (and the package)
at call time; ``create_worker`` injects this adapter, but extraction is only
invoked from the EXTRACT stage (CP28).

Security: the untrusted window text is sent only as the user message; system
instructions are static application prompts (see
:mod:`tender_compliance_api.extraction.prompts`) that document text can never
override (CP26 guardrail).
"""

from __future__ import annotations

import asyncio
import base64
import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel

from tender_compliance_api.config import get_settings
from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmAdapter,
    LlmCallConfig,
    LlmCallError,
    LlmCallResult,
)

#: Fallback when a config omits a timeout / retry budget.
_DEFAULT_TIMEOUT_S: float = 30.0
_DEFAULT_MAX_RETRIES: int = 2
_AZURE_FOUNDRY_API_VERSION = "2024-05-01-preview"


def _azure_foundry_base_url(base_url: str | None) -> tuple[str | None, bool]:
    """Map bare Azure resource hosts to their provider-specific API routes.

    Azure OpenAI resources use the OpenAI v1 surface at ``/openai/v1/``.
    Azure AI Services inference resources use ``/models/chat/completions``
    with an API version and ``api-key`` header. Explicit routes are preserved.
    """
    if not base_url:
        return None, False
    parts = urlsplit(base_url.strip())
    host = (parts.hostname or "").lower()
    if parts.path.strip("/"):
        return base_url, False
    if host.endswith(".openai.azure.com"):
        return urlunsplit((parts.scheme, parts.netloc, "/openai/v1/", "", "")), False
    if host.endswith(".services.ai.azure.com"):
        return urlunsplit((parts.scheme, parts.netloc, "/models/", "", "")), True
    return base_url, False


def _completion_options(config: LlmCallConfig) -> dict[str, object]:
    """Return the existing completion options before provider negotiation."""
    options: dict[str, object] = {}
    if config.max_tokens is not None:
        options["max_tokens"] = config.max_tokens
    if config.temperature is not None:
        options["temperature"] = config.temperature
    if config.seed is not None:
        options["seed"] = config.seed
    return options


def _adapt_unsupported_option(error: Exception, options: dict[str, object]) -> bool:
    """Adapt only explicit 400 unsupported-parameter responses from a provider.

    Some Foundry deployments are configured with an alias that does not expose
    the underlying model family. Use the provider's typed error fields instead
    of guessing from the alias. At most two distinct parameter adjustments are
    possible: ``max_tokens`` to ``max_completion_tokens``, then default
    temperature or sampling seed by omitting the unsupported override.
    """
    if getattr(error, "status_code", None) != 400:
        return False

    code = getattr(error, "code", None)
    parameter = getattr(error, "param", None)
    if parameter == "max_tokens" and code == "unsupported_parameter":
        value = options.pop("max_tokens", None)
        if value is None or "max_completion_tokens" in options:
            return False
        options["max_completion_tokens"] = value
        return True
    if parameter == "temperature" and code in {"unsupported_value", "unsupported_parameter"}:
        return options.pop("temperature", None) is not None
    if parameter == "seed" and code == "unsupported_parameter":
        return options.pop("seed", None) is not None
    return False


def _provider_error_category(error: Exception | None) -> str:
    """Return a bounded, non-sensitive category from the final provider error."""
    if error is None:
        return "provider_error"
    if isinstance(error, LlmCallError) and error.error_category:
        return error.error_category

    code = getattr(error, "code", None)
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", code):
        return code.lower()

    status = getattr(error, "status_code", None)
    if status in {401, 403}:
        return "authentication_error"
    if status == 429:
        return "rate_limit_error"
    if isinstance(status, int) and 400 <= status < 500:
        return "provider_request_error"
    if isinstance(status, int) and status >= 500:
        return "provider_server_error"

    name = type(error).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "connection" in name:
        return "connection_error"
    if "lengthfinishreason" in name or "validation" in name:
        return "invalid_structured_response"
    return "provider_error"


class OpenAiLlmAdapter(LlmAdapter):
    """OpenAI (default ``gpt-4o``) structured-extraction adapter."""

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self._model: str = model or settings.openai_model
        # Empty base_url → OpenAI default endpoint.
        self._base_url: str | None = base_url or (settings.openai_base_url or None)
        self._api_key: str | None = api_key or (settings.openai_api_key or None)

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    def _client(self) -> Any:
        """Build an OpenAI async client.

        Imported lazily so the package is not a hard import-time dependency
        (keeps ``create_worker``/tests green without the package installed).
        The client is typed ``Any`` because we deliberately do not depend on
        the openai type stubs for provider plumbing.
        """

        from openai import AsyncOpenAI

        base_url, azure_models_route = _azure_foundry_base_url(self._base_url)
        return AsyncOpenAI(
            api_key=self._api_key,
            base_url=base_url,
            default_headers=(
                {"api-key": self._api_key}
                if azure_models_route and self._api_key is not None
                else None
            ),
            default_query={"api-version": _AZURE_FOUNDRY_API_VERSION}
            if azure_models_route
            else None,
        )

    async def extract(
        self,
        *,
        system_prompt: str,
        user_text: str,
        response_model: type[BaseModel],
        config: LlmCallConfig,
    ) -> ExtractResult:
        """Call OpenAI with structured output, retrying transient failures.

        Untrusted document text is passed only as the user message.  Raises
        :class:`LlmCallError` only after the bounded retry budget is
        exhausted, so callers get one typed failure per logical call (no
        duplicate run summaries).
        """

        client = self._client()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        timeout = config.timeout_s or _DEFAULT_TIMEOUT_S
        max_retries = config.max_retries or _DEFAULT_MAX_RETRIES
        options = _completion_options(config)
        compatibility_adjustments = 0
        failed_attempts = 0
        last_error: Exception | None = None

        start = time.monotonic()
        while failed_attempts < max_retries and compatibility_adjustments <= 3:
            try:
                completion = await asyncio.wait_for(
                    client.chat.completions.parse(
                        model=config.model,
                        messages=messages,
                        response_format=response_model,
                        **options,
                    ),
                    timeout=timeout,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                choice = completion.choices[0]
                usage = getattr(completion, "usage", None)
                call = LlmCallResult(
                    provider="openai",
                    model=config.model,
                    prompt_version=config.prompt_version,
                    schema_version=config.schema_version,
                    latency_ms=latency_ms,
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                    # Unknown pricing is null, never a fabricated zero.
                    cost_usd=None,
                    finish_reason=getattr(choice, "finish_reason", None),
                    status="completed",
                    call_site=config.call_site,
                )
                response: BaseModel | None = getattr(
                    getattr(choice, "message", None), "parsed", None
                )
                if response is None:
                    raise LlmCallError(
                        "OpenAI returned no parsed structured response "
                        f"(finish_reason={call.finish_reason})",
                        error_category="invalid_structured_response",
                    )
                return ExtractResult(response=response, call=call)
            except Exception as exc:
                last_error = exc
                if compatibility_adjustments < 3 and _adapt_unsupported_option(exc, options):
                    compatibility_adjustments += 1
                    continue
                failed_attempts += 1

        raise LlmCallError(
            "Provider extraction failed after bounded retries and any required "
            "completion-parameter compatibility adjustments",
            error_category=_provider_error_category(last_error),
        ) from None

    async def extract_with_image(
        self,
        *,
        system_prompt: str,
        user_text: str,
        image_bytes: bytes,
        image_mime_type: str,
        response_model: type[BaseModel],
        config: LlmCallConfig,
    ) -> ExtractResult:
        """Call a vision-capable OpenAI-compatible model with one page image."""
        client = self._client()
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{image_mime_type};base64,{encoded_image}"},
                    },
                ],
            },
        ]
        timeout = config.timeout_s or _DEFAULT_TIMEOUT_S
        max_retries = config.max_retries or _DEFAULT_MAX_RETRIES
        options = _completion_options(config)
        compatibility_adjustments = 0
        failed_attempts = 0
        last_error: Exception | None = None
        start = time.monotonic()
        while failed_attempts < max_retries and compatibility_adjustments <= 2:
            try:
                completion = await asyncio.wait_for(
                    client.chat.completions.parse(
                        model=config.model,
                        messages=messages,
                        response_format=response_model,
                        **options,
                    ),
                    timeout=timeout,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                choice = completion.choices[0]
                usage = getattr(completion, "usage", None)
                call = LlmCallResult(
                    provider="openai",
                    model=config.model,
                    prompt_version=config.prompt_version,
                    schema_version=config.schema_version,
                    latency_ms=latency_ms,
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                    cost_usd=None,
                    finish_reason=getattr(choice, "finish_reason", None),
                    status="completed",
                    call_site=config.call_site,
                )
                response: BaseModel | None = getattr(
                    getattr(choice, "message", None), "parsed", None
                )
                if response is None:
                    raise LlmCallError(
                        "OpenAI returned no parsed image response "
                        f"(finish_reason={call.finish_reason})",
                        error_category="invalid_structured_response",
                    )
                return ExtractResult(response=response, call=call)
            except Exception as exc:
                last_error = exc
                if compatibility_adjustments < 2 and _adapt_unsupported_option(exc, options):
                    compatibility_adjustments += 1
                    continue
                failed_attempts += 1
        raise LlmCallError(
            "Provider image validation failed after bounded retries and any "
            "required completion-parameter compatibility adjustments",
            error_category=_provider_error_category(last_error),
        ) from None


__all__ = ["OpenAiLlmAdapter"]
