"""Client for the Wild Flame Smart Fire bio-ethanol burner.

The burner runs its own Wi-Fi access point and serves plain HTTP on 192.168.4.1.

Status:  GET  /info.php -> " usart1=2, usart2=0, usart3=1, usart4=45, usart5=20, usart6=0, usart7=1"
Command: POST /info.php with form body "on=<code>"

All commands are toggles or single steps; there is no absolute "on", "off" or "set flame level".
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from enum import StrEnum

import aiohttp

DEFAULT_HOST = "192.168.4.1"
STATUS_PATH = "/info.php"

CODE_POWER_TOGGLE = "82534KL"
CODE_FLAME_UP = "25896CH"
CODE_FLAME_DOWN = "32768PN"
CODE_CHILD_LOCK_TOGGLE = "36548NP"

FLAME_MIN = 1
FLAME_MAX = 10

_FIELD_RE = re.compile(r"usart(\d+)\s*=\s*(-?\d+(?:\.\d+)?)")


class WildflameError(Exception):
    """Base error."""


class WildflameConnectionError(WildflameError):
    """The burner could not be reached."""


class WildflameResponseError(WildflameError):
    """The burner answered with something unexpected."""


class BurnerState(StrEnum):
    """High-level state derived from the raw fields."""

    OFF = "off"
    WARMING_UP = "warming_up"  # switched on, igniter and burner heating up; flame not adjustable yet (~7 min)
    BURNING = "burning"
    COOLING = "cooling"  # switched off, cooling down (can take over an hour)
    FUEL_EMPTY = "fuel_empty"  # out of fuel; cannot be switched on until refilled
    REFILLING = "refilling"  # tank being refilled; back to off once full
    # Phase code not seen before, possibly an error or a blocked burner. Not "unknown": HA reserves that.
    UNKNOWN_PHASE = "unknown_phase"


# usart2 is the burner's phase code; it matches the status LED. Observed 2026-10-18.
PHASE_BURNING = 0
PHASE_COOLING = 1  # red LED blinking
PHASE_READY = 6  # LED off
# Seen 2026-10-20 after the tank ran empty while burning: cooling down first, then 7 instead of 6.
PHASE_FUEL_EMPTY = 7
# Seen 2026-10-31 while refilling an empty tank: 7 -> 8 -> 6. The fuel level rose from 0 to 100% during it.
PHASE_REFILLING = 8
PHASE_WARMING_UP = 10  # green LED blinking
KNOWN_PHASES = frozenset(
    {
        PHASE_BURNING,
        PHASE_COOLING,
        PHASE_READY,
        PHASE_FUEL_EMPTY,
        PHASE_REFILLING,
        PHASE_WARMING_UP,
    }
)


@dataclass(frozen=True, slots=True)
class WildflameStatus:
    """Parsed status of the burner."""

    raw: dict[int, float]
    fuel_tenths: int  # usart1, 0-10
    phase: int  # usart2, see PHASE_*
    flame_level: int  # usart3, 0 = no flame, 1-10
    humidity: float  # usart4, %
    temperature: float  # usart5, room temperature in °C
    child_lock: bool  # usart6
    powered: bool  # usart7

    @property
    def fuel_percent(self) -> int:
        """Fuel level the way the app shows it."""
        return self.fuel_tenths * 10

    @property
    def state(self) -> BurnerState:
        if self.phase not in KNOWN_PHASES:
            return BurnerState.UNKNOWN_PHASE
        if self.phase == PHASE_FUEL_EMPTY:
            return BurnerState.FUEL_EMPTY
        if self.phase == PHASE_REFILLING:
            return BurnerState.REFILLING
        if self.powered:
            if self.phase == PHASE_WARMING_UP or self.flame_level < FLAME_MIN:
                return BurnerState.WARMING_UP
            return BurnerState.BURNING
        if self.phase == PHASE_COOLING:
            return BurnerState.COOLING
        return BurnerState.OFF

    @classmethod
    def parse(cls, text: str) -> WildflameStatus:
        fields = {int(idx): float(val) for idx, val in _FIELD_RE.findall(text)}
        missing = [i for i in range(1, 8) if i not in fields]
        if missing:
            raise WildflameResponseError(
                f"Status is missing usart{missing}: {text.strip()[:200]!r}"
            )
        return cls(
            raw=fields,
            fuel_tenths=int(fields[1]),
            phase=int(fields[2]),
            flame_level=int(fields[3]),
            humidity=fields[4],
            temperature=fields[5],
            child_lock=fields[6] != 0,
            powered=fields[7] != 0,
        )


class WildflameClient:
    """Talks to one burner. Serialises requests; the burner is a small microcontroller."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str = DEFAULT_HOST,
        timeout: float = 5.0,
    ) -> None:
        self._session = session
        self._url = f"http://{host}{STATUS_PATH}"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._lock = asyncio.Lock()

    async def get_status(self) -> WildflameStatus:
        async with self._lock:
            text = await self._request("GET")
        return WildflameStatus.parse(text)

    async def send_command(self, code: str) -> None:
        async with self._lock:
            await self._request("POST", data={"on": code})

    async def _request(self, method: str, data: dict[str, str] | None = None) -> str:
        try:
            async with self._session.request(
                method, self._url, data=data, timeout=self._timeout
            ) as resp:
                if resp.status != 200:
                    raise WildflameResponseError(f"HTTP {resp.status} from burner")
                # The burner sends no Content-Length and closes the connection to end the body.
                return await resp.text(errors="replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise WildflameConnectionError(f"Cannot reach burner at {self._url}: {err}") from err
