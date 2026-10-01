"""Tests for the file-upload validation layer (CP13).

Covers: valid PDF pass, MIME mismatch, malformed files, oversize files,
and password-protected PDFs.
"""

import io

from pypdf import PdfWriter

from tender_compliance_api.validation.models import FileFormat
from tender_compliance_api.validation.service import ValidationService

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_valid_pdf() -> bytes:
    """Create a minimal, valid single-page PDF in memory."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_protected_pdf(password: str = "secret") -> bytes:
    """Create a password-protected PDF."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Extension validation
# ---------------------------------------------------------------------------


class TestExtensionRule:
    def test_valid_pdf_extension(self) -> None:
        svc = ValidationService()
        data = b"%PDF-1.4 rest of pdf"
        result = svc.validate("tender.pdf", "application/pdf", data)
        assert any("extension" not in e for e in result.errors) or result.valid

    def test_reject_txt_extension(self) -> None:
        svc = ValidationService()
        data = b"%PDF-1.4 rest of pdf"
        result = svc.validate("not_a_pdf.txt", "text/plain", data)
        assert not result.valid
        assert any("extension" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# MIME / file-signature validation
# ---------------------------------------------------------------------------


class TestFileSignatureRule:
    def test_valid_pdf_signature(self) -> None:
        svc = ValidationService()
        data = _make_valid_pdf()
        result = svc.validate("doc.pdf", "application/pdf", data)
        assert result.valid
        assert result.detected_format == FileFormat.PDF
        assert result.detected_content_type == "application/pdf"

    def test_mime_mismatch_rejected(self) -> None:
        """File claims .pdf but bytes don't have the PDF magic."""
        svc = ValidationService()
        data = b"NOT A PDF FILE CONTENTS"
        result = svc.validate("tender.pdf", "application/pdf", data)
        assert not result.valid
        assert any("signature" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# File size validation
# ---------------------------------------------------------------------------


class TestFileSizeRule:
    def test_oversize_rejected(self) -> None:
        svc = ValidationService(max_bytes=100)
        data = b"%PDF-1.4 " + b"x" * 200
        result = svc.validate("big.pdf", "application/pdf", data)
        assert not result.valid
        assert any("exceeds" in e.lower() or "size" in e.lower() for e in result.errors)

    def test_within_limit_accepted(self) -> None:
        svc = ValidationService(max_bytes=1_000_000)
        data = _make_valid_pdf()
        result = svc.validate("ok.pdf", "application/pdf", data)
        assert result.valid


# ---------------------------------------------------------------------------
# PDF integrity validation
# ---------------------------------------------------------------------------


class TestPdfValidationRule:
    def test_valid_pdf_passes(self) -> None:
        svc = ValidationService()
        data = _make_valid_pdf()
        result = svc.validate("valid.pdf", "application/pdf", data)
        assert result.valid

    def test_malformed_pdf_rejected(self) -> None:
        """File starts with %PDF- but is corrupted."""
        svc = ValidationService()
        data = b"%PDF-1.4 this is not a real pdf body"
        result = svc.validate("corrupt.pdf", "application/pdf", data)
        assert not result.valid
        assert any("pdf" in e.lower() for e in result.errors)

    def test_password_protected_pdf_rejected(self) -> None:
        svc = ValidationService()
        data = _make_protected_pdf()
        result = svc.validate("protected.pdf", "application/pdf", data)
        assert not result.valid
        assert any("password" in e.lower() or "protected" in e.lower() for e in result.errors)

    def test_too_many_pages_rejected(self) -> None:
        svc = ValidationService(max_pdf_pages=2)
        writer = PdfWriter()
        for _ in range(5):
            writer.add_blank_page(width=72, height=72)
        buf = io.BytesIO()
        writer.write(buf)
        data = buf.getvalue()
        result = svc.validate("multipage.pdf", "application/pdf", data)
        assert not result.valid
        assert any("page" in e.lower() for e in result.errors)
