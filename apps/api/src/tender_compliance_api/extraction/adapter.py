"""Structured-extraction LLM adapter port (CP26).

Provider-agnostic contract: an :class:`LlmAdapter` receives a trusted source
window (system prompt + the untrusted user window text) and a response
schema, and returns parsed candidates plus an :class:`LlmCallResult` audit
record.  Document services depend on this port, never on a concrete provider,
so swapping providers (e.g. OpenAI -> Anthropic) requires no service rewrites.

Security: untrusted document text is passed only as the ``user_text`` of a
chat message — it never appears in system instructions, so uploaded content
cannot invoke tools or override application instructions (CP26 guardrail).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel


class LlmCallError(RuntimeError):
    """Raised by an :class:`LlmAdapter` when extraction cannot be produced.

    A provider/transport/timeout/parsing failure that exhausts the bounded
    retry budget surfaces as this typed error so callers can distinguish a
    failed call from a valid (possibly empty) response.
    """


@dataclass(frozen=True)
class LlmCallConfig:
    """Parameters for a single LLM extraction call (no secrets here)."""

    provider: str
    model: str
    prompt_version: str
    schema_version: str
    timeout_s: float = 30.0
    max_retries: int = 2
    max_tokens: int | None = None
    temperature: float | None = None
    call_site: str | None = None


@dataclass(frozen=True)
class LlmCallResult:
    """Auditable record of one LLM call.

    Token counts and cost come from the provider when available; ``None``
    means "unknown", never a fabricated zero (per the LLM logging SOP).
    """

    provider: str
    model: str
    prompt_version: str
    schema_version: str
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    finish_reason: str | None
    status: str  # "completed" | "failed"
    error_message: str | None = None
    call_site: str | None = None


@dataclass
class ExtractResult:
    """A single extraction call's parsed response + its audit record."""

    response: BaseModel
    call: LlmCallResult


class LlmAdapter(ABC):
    """Abstract extraction adapter port (CP26).

    Implementations produce a :class:`~tender_compliance_api.extraction.
    schema.RequirementCandidate`-bearing response validated against a trusted
    source window, plus an :class:`LlmCallResult`.  The port is intentionally
    narrow so any provider can implement it.
    """

    @abstractmethod
    async def extract(
        self,
        *,
        system_prompt: str,
        user_text: str,
        response_model: type[BaseModel],
        config: LlmCallConfig,
    ) -> ExtractResult:
        """Extract structured candidates from a trusted source *window*.

        *system_prompt* holds all application/control instructions; the
        untrusted document content is passed only as *user_text*.  The parsed
        response is returned as *response_model* (e.g.
        :class:`~tender_compliance_api.extraction.prompts.ExtractionResponse`).
        """
        raise NotImplementedError


__all__ = [
    "ExtractResult",
    "LlmAdapter",
    "LlmCallConfig",
    "LlmCallError",
    "LlmCallResult",
]
