"""A fake Wild Flame burner that answers like the real one (as captured on 2026-10-18).

Quirks reproduced: body starts with a space, no Content-Length, connection closed after the body.
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs


class FakeBurner:
    def __init__(self) -> None:
        self.fuel = 2
        self.phase = 6
        self.flame = 0
        self.humidity = 45
        self.temperature = 20
        self.child_lock = 0
        self.powered = 0
        self.commands: list[str] = []

    def ignite(self) -> None:
        """Igniter done: burner starts at flame level 5, as observed."""
        self.phase, self.flame = 0, 5
        self._server: asyncio.Server | None = None
        self.port = 0

    def body(self) -> str:
        return (
            f" usart1={self.fuel}, usart2={self.phase}, usart3={self.flame}, "
            f"usart4={self.humidity}, usart5={self.temperature}, usart6={self.child_lock}, "
            f"usart7={self.powered}"
        )

    def apply(self, code: str) -> None:
        self.commands.append(code)
        if code == "82534KL":
            if self.powered:
                self.powered, self.flame, self.phase = 0, 0, 1  # cooling down
            else:
                self.powered, self.flame, self.phase = 1, 0, 10  # igniter heating up
        elif code == "25896CH" and self.powered and self.flame:
            self.flame = min(10, self.flame + 1)
        elif code == "32768PN" and self.powered and self.flame:
            self.flame = max(1, self.flame - 1)
        elif code == "36548NP":
            self.child_lock = 0 if self.child_lock else 1

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    @property
    def host(self) -> str:
        return f"127.0.0.1:{self.port}"

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode().split("\r\n")
        method, path, _ = lines[0].split(" ", 2)
        headers = {k.lower(): v.strip() for k, v in (l.split(":", 1) for l in lines[1:] if ":" in l)}
        if method == "POST":
            data = await reader.readexactly(int(headers.get("content-length", "0")))
            for code in parse_qs(data.decode()).get("on", []):
                self.apply(code)
        if path == "/info.php":
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + self.body().encode())
        else:
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\n")
        await writer.drain()
        writer.close()
