"""Abstract malware-scanning adapter interface (CP13).

Defines the *port* that application services depend on.  Concrete
implementations (ClamAV, etc.) live in production; tests use
:class:`tender_compliance_api.scan.fake.FakeScanner`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class MalwareScannerUnavailableError(RuntimeError):
    """Raised when an upload cannot be scanned safely.

    Upload callers must fail closed on this error. A scanner outage is not
    permission to accept an unscanned tender or OEM document.
    """


@dataclass(frozen=True)
class ScanResult:
    """Outcome of scanning a file for malware.

    Attributes:
        clean: ``True`` if no threat was detected.
        threat_name: Name of the detected threat, or ``None`` if clean.
    """

    clean: bool
    threat_name: str | None = None


class MalwareScanner(ABC):
    """Abstract interface for malware scanning providers.

    Implementations must be async-safe (methods are ``async``) so the
    FastAPI event loop is not blocked.
    """

    @abstractmethod
    async def ready(self) -> bool:
        """Return whether the scanner can accept work right now."""

    @abstractmethod
    async def scan(
        self, filename: str, data: bytes
    ) -> ScanResult:
        """Scan data for malware and return a ScanResult."""
