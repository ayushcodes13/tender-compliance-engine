"""Parser adapter package (CP19).

Exports the abstract :class:`ParserAdapter`, the :class:`PypdfParserAdapter`
for production, and the :class:`FakeParserAdapter` for tests.
"""

from tender_compliance_api.parser.adapter import (
    PageResult,
    ParserAdapter,
    ParseResult,
)
from tender_compliance_api.parser.cleanup import PageCleanup, cleanup_pages
from tender_compliance_api.parser.composite import CompositeParserAdapter
from tender_compliance_api.parser.docx import DocxParserAdapter
from tender_compliance_api.parser.fake import FakeParserAdapter
from tender_compliance_api.parser.pymupdf import PyMuPDFParserAdapter
from tender_compliance_api.parser.pypdf import PypdfParserAdapter

__all__ = [
    "CompositeParserAdapter",
    "DocxParserAdapter",
    "FakeParserAdapter",
    "PageCleanup",
    "PageResult",
    "ParseResult",
    "ParserAdapter",
    "PyMuPDFParserAdapter",
    "PypdfParserAdapter",
    "cleanup_pages",
]
