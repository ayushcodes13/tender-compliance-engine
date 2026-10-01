"""Deterministic fake LLM adapter for tests (CP26).

Returns pre-canned :class:`~tender_compliance_api.extraction.prompts.
ExtractionResponse` objects and records an
:class:`~tender_compliance_api.extraction.adapter.LlmCallResult` per call, so
tests can drive the full extraction path and assert run metadata without any
network access.  This is the only adapter exercised by CI.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from pydantic import BaseModel

from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmAdapter,
    LlmCallConfig,
    LlmCallResult,
)
from tender_compliance_api.extraction.prompts import ExtractionResponse


class FakeLlmAdapter(LlmAdapter):
    """In-memory, deterministic :class:`LlmAdapter` for tests.

    Each :meth:`extract` call pops the next configured response (or returns an
    empty :class:`ExtractionResponse` when exhausted).  A provider-agnostic
    ``LlmCallResult`` is recorded on :attr:`calls` so tests can assert that the
    audit metadata (provider, model, prompt/schema version) reflects the call
    configuration.
    """

    def __init__(self, responses: Sequence[ExtractionResponse] = ()) -> None:
        self._responses: deque[ExtractionResponse] = deque(responses)
        self.calls: list[LlmCallResult] = []

    provider: str = "fake"
    model: str = "fake"

    async def extract(
        self,
        *,
        system_prompt: str,
        user_text: str,
        response_model: type[BaseModel],
        config: LlmCallConfig,
    ) -> ExtractResult:
        # Serve the next canned response; fall back to an empty response so a
        # window with no candidates is representable without network I/O.
        if self._responses:
            response: BaseModel = self._responses.popleft()
        else:
            response = ExtractionResponse()

        call = LlmCallResult(
            provider="fake",
            model="fake",
            prompt_version=config.prompt_version,
            schema_version=config.schema_version,
            latency_ms=0,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            cost_usd=None,
            finish_reason="stop",
            status="completed",
            call_site=config.call_site,
        )
        self.calls.append(call)
        return ExtractResult(response=response, call=call)
