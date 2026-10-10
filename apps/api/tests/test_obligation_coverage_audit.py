"""Fail-closed tests for the independent tender-obligation scan."""

from __future__ import annotations

import asyncio
import struct

import pytest
from pydantic import ValidationError

from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmCallConfig,
    LlmCallResult,
)
from tender_compliance_api.extraction.coverage_audit import (
    CALL_SITE,
    IMAGE_CALL_SITE,
    IMAGE_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TECHNICAL_SECTION_SCOPE,
    ImageObligationCoverageResponse,
    ObligationCoverageResponse,
    _find_potential_omissions,
    audit_page_image_coverage,
    audit_window_coverage,
)
from tender_compliance_api.extraction.fake import FakeLlmAdapter


def test_text_and_image_prompts_share_the_response_obligation_scope() -> None:
    assert PROMPT_VERSION == "1.6.0"
    for prompt in (SYSTEM_PROMPT, IMAGE_SYSTEM_PROMPT):
        assert TECHNICAL_SECTION_SCOPE in prompt
        normalized_prompt = " ".join(prompt.split()).lower()
        assert (
            "selected technical-specification or technical-compliance section"
            in normalized_prompt
        )
        assert (
            "do not search for, infer, or include a requirement from any other tender section"
            in normalized_prompt
        )
        assert "preserve every specification row and nested bullet" in normalized_prompt
        assert (
            'including a subsection called "other requirements" or "terms & conditions"'
            in normalized_prompt
        )
        assert (
            "do not add a summary, interpretation, recommendation, or compliance decision"
            in normalized_prompt
        )
        assert "verbatim" in normalized_prompt
        assert "audit only the supplied source text or page image" in normalized_prompt
        assert (
            "do not search for, infer, or include a requirement from any other tender section"
            in normalized_prompt
        )


def test_coverage_audit_retains_supplier_cure_duty_alongside_buyer_remedies() -> None:
    source = (
        "The purchaser may reject the equipment. "
        "The supplier shall remedy defects within two days. "
        "The purchaser may ban a supplier that fails to comply."
    )
    supplier_duty = "The supplier shall remedy defects within two days."
    adapter = FakeLlmAdapter(
        [ObligationCoverageResponse(quotes=[supplier_duty])]
    )

    result = asyncio.run(audit_window_coverage(source, [], adapter))

    assert result.status == "completed"
    assert result.potential_omissions == (supplier_duty,)


def test_example3_inspection_clause_surfaces_supplier_replacement_duty() -> None:
    source = (
        "Should any inspected or tested Goods fail to conform to the specifications, "
        "the Purchaser may reject the goods and the Supplier shall either replace "
        "the rejected Goods or make alterations necessary to meet specification "
        "requirements free of cost to the Purchaser."
    )
    supplier_duty = (
        "the Supplier shall either replace the rejected Goods or make alterations "
        "necessary to meet specification requirements free of cost to the Purchaser."
    )
    adapter = FakeLlmAdapter([ObligationCoverageResponse(quotes=[supplier_duty])])

    result = asyncio.run(audit_window_coverage(source, [], adapter))

    assert result.status == "completed"
    assert result.potential_omissions == (supplier_duty,)


def test_example3_technical_claim_proof_note_is_a_potential_omission() -> None:
    # Tender page 21 asks for proof supporting claims. The supplied response
    # DOCX page 21 contains only a test graph, so this note is absent from it.
    source_quote = (
        "Valid proof of the document in support of the claim to be enclosed "
        "with the technical bid."
    )
    adapter = FakeLlmAdapter([ObligationCoverageResponse(quotes=[source_quote])])

    result = asyncio.run(audit_window_coverage(source_quote, [], adapter))

    assert result.status == "completed"
    assert result.potential_omissions == (source_quote,)


class _ConfigCapturingAdapter(FakeLlmAdapter):
    def __init__(self, responses=()) -> None:
        super().__init__(responses)
        self.configs: list[LlmCallConfig] = []

    async def extract(self, *, system_prompt, user_text, response_model, config):
        self.configs.append(config)
        return await super().extract(
            system_prompt=system_prompt,
            user_text=user_text,
            response_model=response_model,
            config=config,
        )

    async def extract_with_image(
        self,
        *,
        system_prompt,
        user_text,
        image_bytes,
        image_mime_type,
        response_model,
        config,
    ):
        del system_prompt, user_text, image_bytes, image_mime_type
        self.configs.append(config)
        response = response_model(quotes=[], confidence=1.0, uncertain=False)
        call = LlmCallResult(
            provider=self.provider,
            model=self.model,
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
        return ExtractResult(response=response, call=call)


def test_text_coverage_uses_two_bounded_provider_attempts() -> None:
    adapter = _ConfigCapturingAdapter([ObligationCoverageResponse(quotes=[])])

    result = asyncio.run(audit_window_coverage("No obligations here.", [], adapter))

    assert result.status == "completed"
    assert adapter.configs[0].call_site == CALL_SITE
    assert adapter.configs[0].max_retries == 2


def test_image_coverage_uses_two_bounded_provider_attempts() -> None:
    adapter = _ConfigCapturingAdapter()
    image = b"\x89PNG\r\n\x1a\n" + bytes(8) + struct.pack(">II", 100, 100) + b"x"

    result = asyncio.run(audit_page_image_coverage(3, image, [], adapter))

    assert result.status == "completed"
    assert adapter.configs[0].call_site == IMAGE_CALL_SITE
    assert adapter.configs[0].max_retries == 2


def test_cover_and_contents_window_can_complete_with_no_obligations() -> None:
    source = (
        "Global Tender for the supply of a Diamond Scriber.\n"
        "Section 1 Bid Schedule Pg. 2\n"
        "Section 2 Eligibility Criteria Pg. 3\n"
        "Section 4 Specifications Pg. 10"
    )
    adapter = FakeLlmAdapter([ObligationCoverageResponse(quotes=[])])

    result = asyncio.run(audit_window_coverage(source, [], adapter))

    assert result.status == "completed"
    assert result.potential_omissions == ()


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


def test_example2_utility_row_audit_surfaces_missing_required_details() -> None:
    source_quote = (
        "Vendor shall provide a detailed utility requirement document covering "
        "electrical power including the UPS with backup time and total load, "
        "cooling water, compressed gas, exhaust, vibration limits, floor loading, "
        "and LN₂ infrastructure requirements prior to shipment."
    )
    sampled_output_row = (
        "Vendor shall provide a detailed utility requirement document covering "
        "electrical power including the UPS with backup time and total load, "
        "cooling water, compressed gas, shipment."
    )
    adapter = FakeLlmAdapter([ObligationCoverageResponse(quotes=[source_quote])])

    result = asyncio.run(
        audit_window_coverage(source_quote, [sampled_output_row], adapter)
    )

    assert result.status == "completed"
    assert result.potential_omissions == (source_quote,)


@pytest.mark.parametrize(
    "source_quote",
    [
        pytest.param(
            "Brochure detailing technical specifications and performance, list of "
            "industrial and educational establishments where the items enquired "
            "have been supplied must be provided.",
            id="example2-page20-capability-evidence",
        ),
        pytest.param(
            "BIDDER shall be responsible for installation / demonstration wherever "
            "applicable and for after sales service during the warranty period and "
            "thereafter as mentioned in the contract.",
            id="example3-page8-after-sales-service",
        ),
        pytest.param(
            "The Supplier shall provide such packing of the Goods as is required "
            "to prevent their damage or deterioration during transit to their "
            "final destination.",
            id="example3-page8-packaging-safety",
        ),
    ],
)
def test_sample_source_obligation_absent_from_rows_is_surfaced_for_review(
    source_quote: str,
) -> None:
    # These source-verified clauses were absent from the generated sample rows.
    # The audit only surfaces a potential omission; a reviewer must verify it.
    adapter = FakeLlmAdapter([ObligationCoverageResponse(quotes=[source_quote])])

    result = asyncio.run(audit_window_coverage(source_quote, [], adapter))

    assert result.status == "completed"
    assert result.potential_omissions == (source_quote,)


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


def test_unmatched_text_quote_has_a_stable_reason_for_page_image_fallback() -> None:
    adapter = FakeLlmAdapter(
        [ObligationCoverageResponse(quotes=["A quote outside the source window."])]
    )

    result = asyncio.run(
        audit_window_coverage("The pump shall deliver 12 L/min.", [], adapter)
    )

    assert result.status == "invalid"
    assert result.call.status == "failed"
    assert result.call.error_category == "source_quote_not_found"


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
