"""Malware-scanning adapter package (CP13).

Exports the abstract :class:`MalwareScanner` interface,
:class:`ScanResult`, and the :class:`FakeScanner` test double.
"""

from tender_compliance_api.scan.adapter import MalwareScanner, ScanResult
from tender_compliance_api.scan.fake import FakeScanner

__all__ = [
    "MalwareScanner",
    "ScanResult",
    "FakeScanner",
]
