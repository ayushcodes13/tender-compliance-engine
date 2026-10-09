from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, ValidationError

from tender_compliance_api.export.visual_validation import (
    CALL_SITE,
    PROMPT_VERSION,
    PageImageBatchResponse,
    PageImageQuote,
    PageImageQuoteDecision,
    PageImageValidationResponse,
    validate_quote_on_page_image,
    validate_quotes_on_page_image,
)
from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmAdapter,
    LlmCallError,
    LlmCallResult,
)


class FakeAdapter(LlmAdapter):
    def __init__(self, response: BaseModel | object) -> None:
        self.response = response
        self.call_args: dict[str, object] | None = None

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-vision"

    async def extract(self, **kwargs) -> ExtractResult:
        raise AssertionError("text-only extraction must not be used")

    async def extract_with_image(self, **kwargs) -> ExtractResult:
        self.call_args = kwargs
        return ExtractResult(
            response=self.response,  # type: ignore[arg-type]
            call=LlmCallResult(
                provider=self.provider,
                model=self.model,
                prompt_version=kwargs["config"].prompt_version,
                schema_version=kwargs["config"].schema_version,
                latency_ms=1,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                cost_usd=None,
                finish_reason="stop",
                status="completed",
                call_site=kwargs["config"].call_site,
            ),
        )


def _response(
    *,
    verdict: str = "exact",
    confidence: float = 0.99,
    visible_quote: str,
    reason: str = "Checked against the supplied page image.",
) -> PageImageBatchResponse:
    return PageImageBatchResponse(
        decisions=[
            PageImageQuoteDecision(
                item_id="0",
                verdict=verdict,
                confidence=confidence,
                visible_quote=visible_quote,
                reason=reason,
            )
        ]
    )


def test_visual_validation_accepts_only_exact_quote_from_supplied_page():
    adapter = FakeAdapter(_response(visible_quote="Minimum\naccuracy: ±2 mm"))

    response, call = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote="Minimum accuracy: ±2 mm",
            page_number=7,
            image_bytes=b"page-seven",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert response is not None
    assert response.verdict == "exact"
    assert call.call_site == CALL_SITE
    assert adapter.call_args is not None
    assert adapter.call_args["image_bytes"] == b"page-seven"
    assert adapter.call_args["image_mime_type"] == "image/png"
    assert adapter.call_args["user_text"] == (
        '{"page_number":7,"items":[{"item_id":"0",'
        '"proposed_quote":"Minimum accuracy: ±2 mm"}]}'
    )


def test_visual_validation_ignores_only_layout_whitespace_around_hyphen():
    adapter = FakeAdapter(_response(visible_quote="III-V requirement"))
    response, _call = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote="III -V requirement",
            page_number=10,
            image_bytes=b"page-ten",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )
    assert response is not None
    assert response.verdict == "exact"


def test_visual_batch_validates_each_quote_against_the_same_page():
    adapter = FakeAdapter(
        PageImageBatchResponse(
            decisions=[
                PageImageQuoteDecision(
                    item_id="a",
                    verdict="exact",
                    confidence=0.99,
                    visible_quote="First requirement.",
                    reason="Visible on page.",
                ),
                PageImageQuoteDecision(
                    item_id="b",
                    verdict="exact",
                    confidence=1.0,
                    visible_quote="Second requirement.",
                    reason="Visible on page.",
                ),
            ]
        )
    )

    decisions, call = asyncio.run(
        validate_quotes_on_page_image(
            items=[
                PageImageQuote(item_id="a", proposed_quote="First requirement."),
                PageImageQuote(item_id="b", proposed_quote="Second requirement."),
            ],
            page_number=7,
            image_bytes=b"page-seven",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert set(decisions) == {"a", "b"}
    assert all(decision.verdict == "exact" for decision in decisions.values())
    assert call.status == "completed"
    assert adapter.call_args is not None
    assert adapter.call_args["image_bytes"] == b"page-seven"


@pytest.mark.parametrize(
    "decisions",
    [
        [
            PageImageQuoteDecision(
                item_id="a", verdict="exact", confidence=1.0,
                visible_quote="First requirement.", reason="Visible."
            )
        ],
        [
            PageImageQuoteDecision(
                item_id="a", verdict="exact", confidence=1.0,
                visible_quote="First requirement.", reason="Visible."
            ),
            PageImageQuoteDecision(
                item_id="a", verdict="exact", confidence=1.0,
                visible_quote="First requirement.", reason="Duplicate."
            ),
        ],
        [
            PageImageQuoteDecision(
                item_id="a", verdict="exact", confidence=1.0,
                visible_quote="First requirement.", reason="Visible."
            ),
            PageImageQuoteDecision(
                item_id="extra", verdict="exact", confidence=1.0,
                visible_quote="Unexpected.", reason="Extra."
            ),
        ],
    ],
)
def test_visual_batch_requires_exactly_one_decision_per_requested_item(decisions):
    adapter = FakeAdapter(PageImageBatchResponse(decisions=decisions))

    outcomes, call = asyncio.run(
        validate_quotes_on_page_image(
            items=[
                PageImageQuote(item_id="a", proposed_quote="First requirement."),
                PageImageQuote(item_id="b", proposed_quote="Second requirement."),
            ],
            page_number=7,
            image_bytes=b"page-seven",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert outcomes == {}
    assert call.status == "failed"


def test_visual_batch_rejects_more_than_three_items():
    with pytest.raises(ValueError, match="one to 6 unique items"):
        asyncio.run(
            validate_quotes_on_page_image(
                items=[
                    PageImageQuote(item_id=str(index), proposed_quote=f"Quote {index}")
                    for index in range(7)
                ],
                page_number=7,
                image_bytes=b"page-seven",
                image_mime_type="image/png",
                adapter=FakeAdapter(object()),
            )
        )


def test_visual_validation_ignores_only_standalone_list_bullet_markers():
    adapter = FakeAdapter(
        _response(visible_quote="• Accuracy: ±0.5%\n\uf0a7 Force: 25 kN\n\uf0b7 Power: 220 V")
    )

    response, _ = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote="Accuracy: ±0.5%\nForce: 25 kN\nPower: 220 V",
            page_number=7,
            image_bytes=b"page-seven",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert response is not None
    assert response.verdict == "exact"
    assert adapter.call_args is not None
    assert "Standalone bullet glyphs" in adapter.call_args["system_prompt"]


def test_visual_validation_accepts_visually_confirmed_ocr_open_circle_marker():
    quote = (
        "Digital setting with auto switch-off at set pressure\n"
        "o Secondary back-up pressure setting"
    )
    adapter = FakeAdapter(
        _response(
            visible_quote=(
                "Digital setting with auto switch-off at set pressure\n"
                "Secondary back-up pressure setting"
            ),
            reason="The leading o is a hollow-circle bullet marker.",
        )
    )

    response, _call = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote=quote,
            page_number=18,
            image_bytes=b"page-eighteen",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert response is not None
    assert response.verdict == "exact"
    assert adapter.call_args is not None
    assert 'standalone lowercase "o"' in adapter.call_args["system_prompt"]


def test_visual_validation_requires_reason_for_ocr_open_circle_normalization():
    quote = (
        "Digital setting with auto switch-off at set pressure\n"
        "o Secondary back-up pressure setting"
    )
    adapter = FakeAdapter(
        _response(
            visible_quote=(
                "Digital setting with auto switch-off at set pressure\n"
                "Secondary back-up pressure setting"
            ),
            reason="The words appear to match.",
        )
    )

    response, _call = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote=quote,
            page_number=18,
            image_bytes=b"page-eighteen",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert response is not None
    assert response.verdict == "not_exact"


def test_visual_validation_keeps_visible_leading_letter_o_literal():
    quote = "o Secondary pressure input must be provided."
    adapter = FakeAdapter(_response(visible_quote=quote))

    response, _call = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote=quote,
            page_number=18,
            image_bytes=b"page-eighteen",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert response is not None
    assert response.verdict == "exact"


def test_visual_validation_does_not_ignore_bullet_glyph_inside_requirement_text():
    adapter = FakeAdapter(_response(visible_quote="Accuracy 0.5%"))

    response, _ = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote="Accuracy • 0.5%",
            page_number=7,
            image_bytes=b"page-seven",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert response is not None
    assert response.verdict == "not_exact"


def test_visual_validation_preserves_single_line_legend_symbol():
    adapter = FakeAdapter(_response(visible_quote="= active"))

    response, call = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote="● = active",
            page_number=7,
            image_bytes=b"page-seven",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert response is not None
    assert response.verdict == "not_exact"
    assert call.prompt_version == PROMPT_VERSION == "1.3.0"


@pytest.mark.parametrize(
    ("verdict", "confidence", "visible_quote", "expected_verdict"),
    [
        ("not_exact", 1.0, "Minimum accuracy: ±2 mm", "not_exact"),
        ("cannot_tell", 1.0, "", "cannot_tell"),
        ("exact", 0.98, "Minimum accuracy: ±2 mm", "cannot_tell"),
        ("exact", 1.0, "Minimum accuracy: ±3 mm", "not_exact"),
    ],
)
def test_visual_validation_preserves_abstention_or_rejects_mismatch(
    verdict: str,
    confidence: float,
    visible_quote: str,
    expected_verdict: str,
):
    adapter = FakeAdapter(
        _response(
            verdict=verdict,
            confidence=confidence,
            visible_quote=visible_quote,
        )
    )

    response, _ = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote="Minimum accuracy: ±2 mm",
            page_number=7,
            image_bytes=b"page-seven",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert response is not None
    assert response.verdict == expected_verdict


def test_visual_validation_malformed_response_fails_closed():
    adapter = FakeAdapter(object())

    response, call = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote="Minimum accuracy: ±2 mm",
            page_number=7,
            image_bytes=b"page-seven",
            image_mime_type="image/png",
            adapter=adapter,
        )
    )

    assert response is None
    assert call.status == "failed"
    assert call.call_site == CALL_SITE


def test_visual_validation_provider_error_fails_closed():
    class FailingAdapter(FakeAdapter):
        async def extract_with_image(self, **kwargs) -> ExtractResult:
            raise LlmCallError(
                "provider call failed",
                error_category="image_parse_error",
            )

    response, call = asyncio.run(
        validate_quote_on_page_image(
            proposed_quote="Minimum accuracy: ±2 mm",
            page_number=7,
            image_bytes=b"page-seven",
            image_mime_type="image/png",
            adapter=FailingAdapter(object()),
        )
    )

    assert response is None
    assert call.status == "failed"
    assert call.error_message == "page image validation failed"
    assert call.error_category == "image_parse_error"
    assert call.call_site == CALL_SITE


@pytest.mark.parametrize(
    "payload",
    [
        {
            "verdict": "exact",
            "confidence": "0.99",
            "visible_quote": "Minimum accuracy: ±2 mm",
            "reason": "Checked against the image.",
        },
        {
            "verdict": "exact",
            "confidence": 0.99,
            "visible_quote": "Minimum accuracy: ±2 mm",
            "reason": "Checked against the image.",
            "page_number": 8,
        },
    ],
)
def test_visual_validation_response_rejects_coercible_or_extra_wire_fields(payload):
    with pytest.raises(ValidationError):
        PageImageValidationResponse.model_validate(payload)
