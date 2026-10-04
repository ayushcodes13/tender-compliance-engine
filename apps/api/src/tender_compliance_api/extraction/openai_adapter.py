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
import time
from typing import Any

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
        self._base_url: str | None = base_url or (
            settings.openai_base_url or None
        )
        self._api_key: str | None = api_key or (
            settings.openai_api_key or None
        )

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

        from openai import AsyncOpenAI  # type: ignore[import-not-found]

        return AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

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

        start = time.monotonic()
        last_error: Exception | None = None
        for _attempt in range(1, max_retries + 1):
            try:
                completion = await asyncio.wait_for(
                    client.chat.completions.parse(
                        model=config.model,
                        messages=messages,
                        response_format=response_model,
                        max_tokens=config.max_tokens,
                        temperature=config.temperature,
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
                        f"(finish_reason={call.finish_reason})"
                    )
                return ExtractResult(response=response, call=call)
            except Exception as exc:
                last_error = exc

        raise LlmCallError(
            f"OpenAI extraction failed after {max_retries} attempts: "
            f"{last_error}"
        ) from last_error


__all__ = ["OpenAiLlmAdapter"]
