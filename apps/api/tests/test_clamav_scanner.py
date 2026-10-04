"""Protocol-level tests for the production ClamAV adapter."""

from __future__ import annotations

import asyncio
import struct

import pytest

from tender_compliance_api.scan.adapter import MalwareScannerUnavailableError
from tender_compliance_api.scan.clamav import ClamAvScanner


async def _serve(response: bytes, *, expect_ping: bool = False):
    received = bytearray()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        command = await reader.readuntil(b"\0")
        if expect_ping:
            assert command == b"zPING\0"
        else:
            assert command == b"zINSTREAM\0"
            while True:
                size = struct.unpack("!I", await reader.readexactly(4))[0]
                if size == 0:
                    break
                received.extend(await reader.readexactly(size))
        writer.write(response + b"\0")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port, received


def test_ready_uses_protocol_ping() -> None:
    async def run() -> None:
        server, port, _ = await _serve(b"PONG", expect_ping=True)
        async with server:
            scanner = ClamAvScanner(host="127.0.0.1", port=port, timeout_seconds=1)
            assert await scanner.ready() is True

    asyncio.run(run())


def test_clean_stream_returns_clean() -> None:
    async def run() -> None:
        server, port, received = await _serve(b"stream: OK")
        async with server:
            scanner = ClamAvScanner(host="127.0.0.1", port=port, timeout_seconds=1)
            result = await scanner.scan("tender.pdf", b"trusted test bytes")
            assert result.clean is True
            assert result.threat_name is None
            assert bytes(received) == b"trusted test bytes"

    asyncio.run(run())


def test_found_stream_returns_threat_name() -> None:
    async def run() -> None:
        server, port, _ = await _serve(b"stream: Win.Test.EICAR_HDB-1 FOUND")
        async with server:
            scanner = ClamAvScanner(host="127.0.0.1", port=port, timeout_seconds=1)
            result = await scanner.scan("eicar.com", b"test")
            assert result.clean is False
            assert result.threat_name == "Win.Test.EICAR_HDB-1"

    asyncio.run(run())


def test_clamd_error_fails_closed() -> None:
    async def run() -> None:
        server, port, _ = await _serve(b"stream: INSTREAM size limit exceeded. ERROR")
        async with server:
            scanner = ClamAvScanner(host="127.0.0.1", port=port, timeout_seconds=1)
            with pytest.raises(MalwareScannerUnavailableError):
                await scanner.scan("large.pdf", b"test")

    asyncio.run(run())


def test_unreachable_scanner_fails_closed() -> None:
    scanner = ClamAvScanner(host="127.0.0.1", port=1, timeout_seconds=0.1)

    with pytest.raises(MalwareScannerUnavailableError):
        asyncio.run(scanner.scan("tender.pdf", b"test"))
