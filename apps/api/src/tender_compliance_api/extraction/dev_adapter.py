"""Deterministic development LLM adapter (CP26).

Used **only** in ``APP_ENV=development`` when no ``OPENAI_API_KEY`` is
configured, so the full extraction pipeline is exercisable locally without
network access to a model provider.

This adapter does **not** replace the real OpenAI adapter.  It applies a
small, deterministic rule set to find text that looks like a technical
requirement (modal language: *shall*, *must*, *required*, *shall not*,
*must not*) and emits :class:`~tender_compliance_api.extraction.schema
.RequirementCandidate` objects whose ``raw_source`` is a verbatim
substring of the trusted window text — so the CP25 citation-substring
boundary is still enforced by the extraction orchestrator.

Every candidate from this adapter is marked ``CONFIRMED`` *only* when its
``raw_source`` actually appears in the window text.  The orchestrator's
:func:`~tender_compliance_api.extraction.extractor._to_record` validation
will reject any candidate whose ``raw_source`` cannot be found in
``source_text``, so fabrication is impossible — the adapter can only
surface text already present in the page.

Security: untrusted document text is passed only as ``user_text`` (never in
system instructions), matching the CP26 guardrail that document content
cannot override application instructions.
"""

from __future__ import annotations

import re
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
from tender_compliance_api.extraction.schema import (
    RequirementCandidate,
    RequirementType,
    UncertaintyLevel,
)

#: Lines whose modal language marks them as extractable requirements.
#: Each pattern matches any line containing the modal verb, so obligation vs
#: prohibition is distinguished separately (a "shall not" line is a prohibition,
#: a bare "shall" line is an obligation).
_REQUIREMENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bshall\b", re.IGNORECASE),
    re.compile(r"\bmust\b", re.IGNORECASE),
    re.compile(r"\brequired\b", re.IGNORECASE),
]

#: Detect prohibition modal language ("shall not", "must not").
_PROHIBITION_RE = re.compile(r"\bshall\s+not\b|\bmust\s+not\b", re.IGNORECASE)

#: Clause-number prefix (e.g. "1." "2.3" "4.1.2").
_CLAUSE_PREFIX_RE = re.compile(r"^(\s*)(\d+(?:\.\d+)*\.?)\s+(.*)")


class DevLlmAdapter(LlmAdapter):
    """Deterministic, rule-based :class:`LlmAdapter` for local development.

    Scans each line of ``user_text`` for modal-language requirements and
    emits candidates whose ``raw_source`` is the verbatim line — guaranteeing
    the CP25 source-substring boundary will pass.  Returns an empty
    :class:`ExtractionResponse` when no requirement-like text is found,
    matching the contract that "nothing is invented from empty input."
    """

    provider: str = "dev"
    model: str = "deterministic-rules"

    def __init__(self, responses: Sequence[ExtractionResponse] = ()) -> None:
        """Optionally seed with pre-canned responses (for hybrid testing)."""
        self._seed: deque[ExtractionResponse] = deque(responses)
        self.calls: list[LlmCallResult] = []

    async def extract(
        self,
        *,
        system_prompt: str,
        user_text: str,
        response_model: type[BaseModel],
        config: LlmCallConfig,
    ) -> ExtractResult:
        """Return deterministic candidates extracted from *user_text*.

        If a pre-canned response is queued (for tests), serve it first.
        Otherwise, scan *user_text* for modal-language requirements.

        Security: untrusted document text is only read as ``user_text``;
        the system prompt (application instructions) is never derived from it.
        """

        response: BaseModel
        if self._seed:
            response = self._seed.popleft()
        else:
            response = self._extract_from_text(user_text)

        call = LlmCallResult(
            provider="dev",
            model="deterministic-rules",
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

    def _extract_from_text(self, text: str) -> ExtractionResponse:
        """Deterministically find requirement candidates in *text*.

        Each candidate's ``raw_source`` is a verbatim line or clause from
        *text*, ensuring the extractor's source-validation gate cannot
        reject it as fabricated.
        """

        candidates: list[RequirementCandidate] = []

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            clause_number: str | None = None
            content = stripped

            match = _CLAUSE_PREFIX_RE.match(stripped)
            if match:
                clause_number = match.group(2).rstrip(".")
                content = match.group(3).strip()

            for pattern in _REQUIREMENT_PATTERNS:
                if pattern.search(content):
                    raw_source = stripped  # verbatim line — substring-safe
                    normalized_text = content

                    is_prohibition = bool(_PROHIBITION_RE.search(content))
                    req_type = (
                        RequirementType.PROHIBITION
                        if is_prohibition
                        else RequirementType.OBLIGATION
                    )

                    candidates.append(
                        RequirementCandidate(
                            normalized_text=normalized_text,
                            raw_source=raw_source,
                            requirement_type=req_type,
                            uncertainty=UncertaintyLevel.CONFIRMED,
                            clause_section=clause_number,
                        )
                    )
                    break  # one candidate per line, first pattern wins

        return ExtractionResponse(candidates=candidates)


__all__ = ["DevLlmAdapter"]
