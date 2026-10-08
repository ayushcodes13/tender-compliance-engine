from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, ValidationError

from tender_compliance_api.export.visual_validation import (
    CALL_SITE,
    PageImageValidationResponse,
    validate_quote_on_page_image,
)
from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmAdapter,
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
    *, verdict: str = "exact", confidence: float = 0.99, visible_quote: str
) -> PageImageValidationResponse:
    return PageImageValidationResponse(
        verdict=verdict,
        confidence=confidence,
        visible_quote=visible_quote,
        reason="Checked against the supplied page image.",
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
        '{"page_number":7,"proposed_quote":"Minimum accuracy: ±2 mm"}'
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
            raise RuntimeError("provider unavailable")

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
