"""Tests for the deterministic development LLM adapter (CP26).

Covers:
- Extracts requirement candidates from modal-language text (shall, must, required).
- Distinguishes obligation vs prohibition (shall not, must not).
- Extracts clause/section numbers from numbered prefixes.
- Returns CONFIRMED uncertainty so candidates are persistable.
- Returns empty response when no requirement-like text is present.
- Seeds pre-canned responses when provided.
- Records an LlmCallResult audit row per call.
"""

from __future__ import annotations

import asyncio

from tender_compliance_api.extraction.adapter import LlmCallConfig
from tender_compliance_api.extraction.dev_adapter import DevLlmAdapter
from tender_compliance_api.extraction.prompts import ExtractionResponse
from tender_compliance_api.extraction.schema import RequirementType


def _make_config() -> LlmCallConfig:
    return LlmCallConfig(
        provider="dev",
        model="deterministic-rules",
        prompt_version="1.0.0",
        schema_version="1.0.0",
        call_site="extract_candidates",
    )


# --- Helper to run async extract ---

def _run_extract(adapter: DevLlmAdapter, text: str) -> ExtractionResponse:
    return asyncio.run(_async_extract(adapter, text))


async def _async_extract(adapter: DevLlmAdapter, text: str) -> ExtractionResponse:
    result = await adapter.extract(
        system_prompt="<system instructions>",
        user_text=text,
        response_model=ExtractionResponse,
        config=_make_config(),
    )
    return result.response


# --- Obligation detection ---


class TestObligationExtraction:
    def test_extracts_shall_requirements(self) -> None:
        text = (
            "1. The controller shall have a processing speed of at least 2.5 GHz.\n"
            "2. Response time shall be measured in milliseconds."
        )
        resp = _run_extract(DevLlmAdapter(), text)
        assert len(resp.candidates) == 2
        assert all(c.uncertainty.value == "confirmed" for c in resp.candidates)
        assert all(c.requirement_type is RequirementType.OBLIGATION for c in resp.candidates)

    def test_extracts_must_requirements(self) -> None:
        text = "The device must comply with IP65 ingress protection rating."
        resp = _run_extract(DevLlmAdapter(), text)
        assert len(resp.candidates) == 1
        assert resp.candidates[0].requirement_type is RequirementType.OBLIGATION

    def test_extracts_required_requirements(self) -> None:
        text = "Minimum 1000 concurrent users are required for the system."
        resp = _run_extract(DevLlmAdapter(), text)
        assert len(resp.candidates) == 1
        assert resp.candidates[0].requirement_type is RequirementType.OBLIGATION


# --- Prohibition detection ---


class TestProhibitionExtraction:
    def test_shall_not_is_prohibition(self) -> None:
        text = "4. Response time shall not exceed 100 milliseconds under full load."
        resp = _run_extract(DevLlmAdapter(), text)
        assert len(resp.candidates) == 1
        assert resp.candidates[0].requirement_type is RequirementType.PROHIBITION

    def test_must_not_is_prohibition(self) -> None:
        text = "5. The device must not consume more than 50W under full load."
        resp = _run_extract(DevLlmAdapter(), text)
        assert len(resp.candidates) == 1
        assert resp.candidates[0].requirement_type is RequirementType.PROHIBITION


# --- Clause number extraction ---


class TestClauseNumberExtraction:
    def test_extracts_clauses_from_numbered_prefixes(self) -> None:
        text = (
            "1.1 Speed shall be 2.5 GHz.\n"
            "1.2 Temperature shall be -20 to +60 C.\n"
            "2.0 Humidity must be below 85%."
        )
        resp = _run_extract(DevLlmAdapter(), text)
        assert len(resp.candidates) == 3
        assert resp.candidates[0].clause_section == "1.1"
        assert resp.candidates[1].clause_section == "1.2"
        assert resp.candidates[2].clause_section == "2.0"

    def test_no_clause_number_when_unnumbered(self) -> None:
        text = "The controller shall have a processing speed of at least 2.5 GHz."
        resp = _run_extract(DevLlmAdapter(), text)
        assert len(resp.candidates) == 1
        assert resp.candidates[0].clause_section is None


# --- Empty / non-requirement text ---


class TestEmptyText:
    def test_no_requirements_yields_empty_response(self) -> None:
        text = (
            "Technical Requirements for Industrial Control System\n\n"
            "This document describes the product."
        )
        resp = _run_extract(DevLlmAdapter(), text)
        assert len(resp.candidates) == 0

    def test_empty_string_yields_empty_response(self) -> None:
        resp = _run_extract(DevLlmAdapter(), "")
        assert len(resp.candidates) == 0


# --- raw_source is verbatim substring of user_text ---


class TestSourceSubstringGuarantee:
    def test_raw_source_is_exact_substring(self) -> None:
        """Every candidate's raw_source must be a verbatim substring of the
        user_text, so the CP25 source-substring boundary cannot reject it."""
        text = "1. The controller shall have a processing speed of at least 2.5 GHz."
        resp = _run_extract(DevLlmAdapter(), text)
        assert len(resp.candidates) == 1
        normalized = " ".join(text.split())
        raw_normalized = " ".join(resp.candidates[0].raw_source.split())
        assert raw_normalized in normalized


# --- Seed responses override rule-based extraction ---


class TestSeededResponses:
    def test_seeded_responses_take_priority(self) -> None:
        from tender_compliance_api.extraction.schema import (
            RequirementCandidate,
            UncertaintyLevel,
        )
        seeded = ExtractionResponse(
            candidates=[
                RequirementCandidate(
                    normalized_text="Seeded requirement text",
                    raw_source="Seeded requirement text",
                    requirement_type=RequirementType.OBLIGATION,
                    uncertainty=UncertaintyLevel.CONFIRMED,
                )
            ]
        )
        adapter = DevLlmAdapter(responses=[seeded])
        text = "1. The controller shall have a processing speed of at least 2.5 GHz."
        resp = _run_extract(adapter, text)
        assert len(resp.candidates) == 1
        assert resp.candidates[0].normalized_text == "Seeded requirement text"


# --- Audit metadata ---


class TestAuditMetadata:
    def test_call_recorded_with_correct_provider(self) -> None:
        adapter = DevLlmAdapter()
        _run_extract(adapter, "The device must comply with IP65 rating.")
        assert len(adapter.calls) == 1
        call = adapter.calls[0]
        assert call.provider == "dev"
        assert call.model == "deterministic-rules"
        assert call.status == "completed"
        assert call.call_site == "extract_candidates"
