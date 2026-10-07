"""Safe, stable messages for unexpected failures exposed by the API."""

UNEXPECTED_REQUEST_FAILURE = (
    "The request could not be completed. Please retry. If it keeps failing, "
    "contact support and share the request ID."
)
PROCESSING_STAGE_FAILURE = (
    "This processing stage did not complete. Retry processing. If it keeps "
    "failing, contact support and share the request ID."
)
EXPORT_FAILURE = (
    "The export could not be completed. Please retry. If it keeps failing, "
    "contact support and share the request ID."
)
PAGE_TEXT_FAILURE = (
    "Text extraction failed for this page. Review the original page before "
    "relying on extracted text."
)
PAGE_RENDER_FAILURE = (
    "Page preview rendering failed. The source document remains available "
    "for review."
)
PAGE_IMAGE_STORAGE_FAILURE = "The page preview could not be stored."
PAGE_OCR_FAILURE = (
    "OCR could not process this page. Review the original page before "
    "relying on extracted text."
)


__all__ = [
    "EXPORT_FAILURE",
    "PAGE_IMAGE_STORAGE_FAILURE",
    "PAGE_OCR_FAILURE",
    "PAGE_RENDER_FAILURE",
    "PAGE_TEXT_FAILURE",
    "PROCESSING_STAGE_FAILURE",
    "UNEXPECTED_REQUEST_FAILURE",
]
