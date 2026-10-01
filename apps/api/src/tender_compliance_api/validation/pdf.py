"""PDF-specific validation rule (CP13).

Uses ``pypdf`` to detect:

* Malformed / unreadable PDFs (parse errors).
* Password-protected PDFs (encrypted).
* Excessive page counts.

The rule never *executes* embedded content — ``pypdf`` only reads the
structural catalog, it does not interpret JavaScript or render pages.
"""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from tender_compliance_api.validation.rules import FileValidationRule

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 500


class PdfValidationRule(FileValidationRule):
    """Validate a PDF file for structural integrity and security flags.

    Args:
        max_pages: Reject PDFs with more than this many pages.
    """

    name = "pdf"

    def __init__(self, max_pages: int = DEFAULT_MAX_PAGES) -> None:
        self._max_pages = max_pages

    def check(
        self, filename: str, content_type: str | None, data: bytes
    ) -> list[str]:
        # Only run on files that appear to be PDFs (signature already
        # verified by FileSignatureRule, but we double-check here for
        # safety when this rule is invoked standalone).
        if not data.startswith(b"%PDF-"):
            return []

        try:
            reader = PdfReader(io.BytesIO(data))
        except PdfReadError as exc:
            return [
                f"PDF could not be read (malformed or corrupted): {exc}"
            ]
        except Exception as exc:  # noqa: BLE001 — any parse failure = reject
            logger.warning("Unexpected pypdf error for %s: %s", filename, exc)
            return [f"PDF parsing failed: {exc!r}"]

        errors: list[str] = []

        # --- Password / encryption ---
        if reader.is_encrypted:
            errors.append(
                "PDF is password-protected; password-protected documents "
                "are not supported in Phase 1"
            )
            return errors  # don't attempt page-count on encrypted PDFs

        # --- Page count ---
        try:
            page_count = len(reader.pages)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Could not determine PDF page count: {exc!r}")
            return errors

        if page_count > self._max_pages:
            errors.append(
                f"PDF has {page_count} pages; maximum allowed is "
                f"{self._max_pages}"
            )

        # --- Embedded files / JavaScript (warnings only) ---
        # We never execute these — pypdf only reads structural metadata,
        # never interprets or executes embedded scripts.  The check below
        # simply logs warnings for reviewer awareness.
        try:
            root = reader.trailer["/Root"]
            if hasattr(root, "get"):
                names = root.get("/Names")
                if names and hasattr(names, "get"):
                    if names.get("/EmbeddedFiles") is not None:
                        logger.warning(
                            "PDF %s contains embedded file attachments", filename
                        )
                if root.get("/JS") is not None:
                    logger.warning(
                        "PDF %s contains embedded JavaScript (not executed)",
                        filename,
                    )
        except Exception:  # noqa: BLE001
            pass  # non-fatal — skip the warning check

        return errors
