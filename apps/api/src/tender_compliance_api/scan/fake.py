"""In-memory fake malware scanner (CP13).

Used by tests and local development.  Always reports files as clean
unless they contain a known test signature.
"""

from __future__ import annotations

from tender_compliance_api.scan.adapter import MalwareScanner, ScanResult

# A deliberately innocuous byte sequence that test code can embed in a
# file to simulate an infected upload.  This mirrors the EICAR convention
# without introducing a real malware signature.
TEST_INFECTED_SIGNATURE = b"EICAR-STANDARD-ANTIVIRUS-TEST"


class FakeScanner(MalwareScanner):
    """No-op scanner that always reports files as clean.

    Tests that need to simulate a positive scan can subclass this and
    override :meth:`scan`, or embed ``TEST_INFECTED_SIGNATURE`` in the
    upload data.
    """

    async def scan(
        self, filename: str, data: bytes
    ) -> ScanResult:
        if TEST_INFECTED_SIGNATURE in data:
            return ScanResult(clean=False, threat_name="EICAR-Test-File")
        return ScanResult(clean=True, threat_name=None)
