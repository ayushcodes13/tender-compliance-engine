"""Async ClamAV scanner using clamd's documented TCP protocol."""

from __future__ import annotations

import asyncio
import contextlib
import struct

from tender_compliance_api.scan.adapter import (
    MalwareScanner,
    MalwareScannerUnavailableError,
    ScanResult,
)


class ClamAvScanner(MalwareScanner):
    """Scan upload bytes through an internal clamd TCP service."""

    _chunk_size = 1024 * 1024

    def __init__(self, *, host: str, port: int = 3310, timeout_seconds: float = 30.0):
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds

    async def ready(self) -> bool:
        """Return True only when clamd responds to a protocol-level PING."""
        try:
            response = await self._exchange_ping()
        except MalwareScannerUnavailableError:
            return False
        return response == "PONG"

    async def scan(self, filename: str, data: bytes) -> ScanResult:
        """Stream bytes to clamd and return a clean/infected result."""
        del filename
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_connection(self._host, self._port)
                try:
                    writer.write(b"zINSTREAM\0")
                    await writer.drain()

                    for offset in range(0, len(data), self._chunk_size):
                        chunk = data[offset : offset + self._chunk_size]
                        writer.write(struct.pack("!I", len(chunk)))
                        writer.write(chunk)
                        await writer.drain()

                    writer.write(struct.pack("!I", 0))
                    await writer.drain()
                    response = await reader.readuntil(b"\0")
                finally:
                    writer.close()
                    with contextlib.suppress(Exception):
                        await writer.wait_closed()
        except MalwareScannerUnavailableError:
            raise
        except (TimeoutError, OSError, asyncio.IncompleteReadError) as exc:
            raise MalwareScannerUnavailableError(
                "Malware scanner did not complete the scan"
            ) from exc

        return self._parse_scan_response(response)

    async def _exchange_ping(self) -> str:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_connection(self._host, self._port)
                try:
                    writer.write(b"zPING\0")
                    await writer.drain()
                    response = await reader.readuntil(b"\0")
                finally:
                    writer.close()
                    with contextlib.suppress(Exception):
                        await writer.wait_closed()
        except (TimeoutError, OSError, asyncio.IncompleteReadError) as exc:
            raise MalwareScannerUnavailableError(
                "Malware scanner is unavailable"
            ) from exc
        return response.rstrip(b"\0\r\n").decode("utf-8", errors="replace").strip()

    @staticmethod
    def _parse_scan_response(response: bytes) -> ScanResult:
        text = response.rstrip(b"\0\r\n").decode("utf-8", errors="replace").strip()
        if text.endswith(" OK"):
            return ScanResult(clean=True)
        if text.endswith(" FOUND"):
            detail = text.split(":", 1)[-1].removesuffix(" FOUND").strip()
            return ScanResult(clean=False, threat_name=detail or "malware")
        raise MalwareScannerUnavailableError(
            "Malware scanner returned an unusable response"
        )
