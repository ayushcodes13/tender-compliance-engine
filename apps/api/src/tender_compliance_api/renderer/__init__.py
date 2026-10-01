"""Page renderer adapter package (CP20).

Exports the abstract :class:`RendererAdapter`, the
:class:`PymupdfRendererAdapter` for production rendering, and the
:class:`FakeRendererAdapter` for tests.
"""

from tender_compliance_api.renderer.adapter import (
    RendererAdapter,
    RenderPageResult,
    RenderResult,
)
from tender_compliance_api.renderer.fake import FakeRendererAdapter
from tender_compliance_api.renderer.pymupdf import PymupdfRendererAdapter

__all__ = [
    "FakeRendererAdapter",
    "PymupdfRendererAdapter",
    "RenderPageResult",
    "RenderResult",
    "RendererAdapter",
]
