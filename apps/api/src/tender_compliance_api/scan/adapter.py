"""Abstract malware-scanning adapter interface (CP13).

Defines the *port* that application services depend on.  Concrete
implementations (ClamAV, etc.) live in production; tests use
:class:`tender_compliance_api.scan.fake.FakeScanner`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


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
    async def scan(
        self, filename: str, data: bytes
    ) -> ScanResult:
        """Scan ``data`` for malware and return a :class:`ScanResult`."""
