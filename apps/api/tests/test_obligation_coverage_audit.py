"""Fail-closed tests for the independent tender-obligation scan."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from tender_compliance_api.extraction.coverage_audit import (
    CALL_SITE,
    ImageObligationCoverageResponse,
    ObligationCoverageResponse,
    _find_potential_omissions,
    audit_window_coverage,
)
from tender_compliance_api.extraction.fake import FakeLlmAdapter


def test_strict_response_rejects_wrong_types_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ObligationCoverageResponse(quotes=[123])
    with pytest.raises(ValidationError):
        ObligationCoverageResponse(quotes=[], complete=True)
    with pytest.raises(ValidationError):
        ImageObligationCoverageResponse(
            quotes=[
                {
                    "source_quote": "Temperature must stay below 90 C.",
                    "confidence": 0.999,
                    "bbox": {"x": 0.9, "y": 0.1, "width": 0.2, "height": 0.2},
                }
            ],
            confidence=0.999,
            uncertain=False,
        )


def test_detects_exact_auditor_quote_not_emitted_by_primary_pass() -> None:
    text = "The pump shall deliver 12 L/min. The motor shall be IP55 rated."
    omissions = _find_potential_omissions(
        text,
        ["The pump shall deliver 12 L/min.", "The motor shall be IP55 rated."],
        ["The pump shall deliver 12 L/min."],
    )
    assert omissions == ("The motor shall be IP55 rated.",)


def test_accepts_split_rows_that_cover_every_non_whitespace_source_character() -> None:
    quote = "The pump shall deliver 12 L/min under continuous operation."
    assert _find_potential_omissions(
        quote,
        [quote],
        ["The pump shall deliver 12 L/min", "under continuous operation."],
    ) == ()


def test_rejects_auditor_quote_outside_its_authorized_window() -> None:
    assert _find_potential_omissions(
        "The pump shall deliver 12 L/min.",
        ["The motor shall be IP55 rated."],
        [],
    ) is None


def test_audit_call_is_logged_and_unmatched_quote_is_returned() -> None:
    from tender_compliance_api.extraction.coverage_audit import ObligationCoverageResponse

    adapter = FakeLlmAdapter(
        [ObligationCoverageResponse(quotes=["The motor shall be IP55 rated."])]
    )
    logged = []

    async def run() -> None:
        async def log(call) -> None:
            logged.append(call)

        result = await audit_window_coverage(
            "The motor shall be IP55 rated.", [], adapter
        )
        await log(result.call)
        assert result.status == "completed"
        assert result.potential_omissions == ("The motor shall be IP55 rated.",)

    asyncio.run(run())
    assert len(logged) == 1
    assert logged[0].call_site == CALL_SITE
