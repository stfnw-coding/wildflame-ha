"""Polling coordinator and command logic for the Wild Flame burner."""

from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CODE_FLAME_DOWN,
    CODE_FLAME_UP,
    CODE_POWER_TOGGLE,
    FLAME_MAX,
    FLAME_MIN,
    BurnerState,
    WildflameClient,
    WildflameError,
    WildflameStatus,
)
from .const import DOMAIN, FLAME_STEP_DELAY_SECONDS, POWER_TOGGLE_GUARD_SECONDS, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type WildflameConfigEntry = ConfigEntry[WildflameCoordinator]


class WildflameCoordinator(DataUpdateCoordinator[WildflameStatus]):
    """Polls the burner and sends commands safely (all commands are toggles or steps)."""

    config_entry: WildflameConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: WildflameConfigEntry, client: WildflameClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self._command_lock = asyncio.Lock()
        self._power_pending_since: float | None = None
        self._power_pending_from: bool | None = None

    async def _async_update_data(self) -> WildflameStatus:
        try:
            status = await self.client.get_status()
        except WildflameError as err:
            raise UpdateFailed(str(err)) from err
        if self._power_pending_from is not None and status.powered != self._power_pending_from:
            self._clear_power_guard()
        return status

    def _clear_power_guard(self) -> None:
        self._power_pending_since = None
        self._power_pending_from = None

    def _power_guard_active(self) -> bool:
        if self._power_pending_since is None:
            return False
        if time.monotonic() - self._power_pending_since > POWER_TOGGLE_GUARD_SECONDS:
            self._clear_power_guard()
            return False
        return True

    async def async_set_power(self, on: bool) -> None:
        async with self._command_lock:
            status = await self._fresh_status()
            if status.powered == on:
                return
            if self._power_guard_active():
                raise HomeAssistantError(
                    "De haard verwerkt het vorige aan/uit-commando nog; probeer het zo opnieuw."
                )
            if on:
                if status.child_lock:
                    raise HomeAssistantError("Het kinderslot van de haard staat aan.")
                if status.state is BurnerState.COOLING:
                    raise HomeAssistantError(
                        "De haard koelt nog af (rood lampje) en kan pas weer aan als dat klaar is."
                    )
            await self._send(CODE_POWER_TOGGLE)
            self._power_pending_since = time.monotonic()
            self._power_pending_from = status.powered
        await self.async_request_refresh()

    async def async_set_flame_level(self, level: int) -> None:
        level = max(FLAME_MIN, min(FLAME_MAX, level))
        async with self._command_lock:
            status = await self._fresh_status()
            if status.state is not BurnerState.BURNING:
                raise HomeAssistantError(
                    "De vlamhoogte kan alleen worden aangepast als de haard brandt."
                )
            if status.child_lock:
                raise HomeAssistantError("Het kinderslot van de haard staat aan.")
            steps = level - status.flame_level
            code = CODE_FLAME_UP if steps > 0 else CODE_FLAME_DOWN
            for i in range(abs(steps)):
                if i:
                    await asyncio.sleep(FLAME_STEP_DELAY_SECONDS)
                await self._send(code)
        await self.async_request_refresh()

    async def _fresh_status(self) -> WildflameStatus:
        try:
            status = await self.client.get_status()
        except WildflameError as err:
            raise HomeAssistantError(f"Haard niet bereikbaar: {err}") from err
        self.async_set_updated_data(status)
        return status

    async def _send(self, code: str) -> None:
        try:
            await self.client.send_command(code)
        except WildflameError as err:
            raise HomeAssistantError(f"Commando naar de haard mislukt: {err}") from err
