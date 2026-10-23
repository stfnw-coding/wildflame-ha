"""Polling coordinator and command logic for the Wild Flame burner."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CODE_CHILD_LOCK_TOGGLE,
    CODE_FLAME_DOWN,
    CODE_FLAME_UP,
    CODE_POWER_TOGGLE,
    FLAME_MAX,
    FLAME_MIN,
    BurnerState,
    WildflameClient,
    WildflameConnectionError,
    WildflameError,
    WildflameStatus,
)
from .const import (
    DOMAIN,
    FLAME_STEP_DELAY_SECONDS,
    POWER_TOGGLE_GUARD_SECONDS,
    SCAN_INTERVAL,
)
from .wifi import WifiRecovery

_LOGGER = logging.getLogger(__name__)

type WildflameConfigEntry = ConfigEntry[WildflameCoordinator]


def _error(key: str, **placeholders: str) -> HomeAssistantError:
    """The burner could not be reached or did not take the command.

    Shown to the user in their own language (see "exceptions" in strings.json).
    """
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


def _refused(key: str, **placeholders: str) -> ServiceValidationError:
    """The burner's current state does not allow the action; nothing went wrong."""
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


class _ToggleGuard:
    """Refuses a second toggle until the burner reports the change, or the guard times out.

    A second toggle sent before the first one shows up would undo it.
    """

    def __init__(self) -> None:
        self._since: float | None = None
        self._from: bool | None = None

    def start(self, current: bool) -> None:
        self._since, self._from = time.monotonic(), current

    def observe(self, current: bool) -> None:
        if self._from is not None and current != self._from:
            self._since = self._from = None

    def active(self) -> bool:
        if self._since is None:
            return False
        if time.monotonic() - self._since > POWER_TOGGLE_GUARD_SECONDS:
            self._since = self._from = None
            return False
        return True


class WildflameCoordinator(DataUpdateCoordinator[WildflameStatus]):
    """Polls the burner and sends commands safely (all commands are toggles or steps)."""

    config_entry: WildflameConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WildflameConfigEntry,
        client: WildflameClient,
        wifi_recovery: WifiRecovery | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            # Only write entity states when the burner reports something new.
            always_update=False,
        )
        self.client = client
        self._wifi_recovery = wifi_recovery
        self._command_lock = asyncio.Lock()
        self._power_guard = _ToggleGuard()
        self._child_lock_guard = _ToggleGuard()
        self._warned_phases: set[int] = set()

    @override
    async def _async_update_data(self) -> WildflameStatus:
        try:
            status = await self.client.get_status()
        except WildflameConnectionError as err:
            if self._wifi_recovery:
                self._wifi_recovery.async_burner_unreachable()
            raise UpdateFailed(str(err)) from err
        except WildflameError as err:
            raise UpdateFailed(str(err)) from err
        if self._wifi_recovery:
            self._wifi_recovery.async_burner_reachable()
        self._power_guard.observe(status.powered)
        self._child_lock_guard.observe(status.child_lock)
        if status.state is BurnerState.UNKNOWN_PHASE and status.phase not in self._warned_phases:
            self._warned_phases.add(status.phase)
            _LOGGER.warning(
                "The burner reports phase code %s, which this integration does not know yet. "
                "Please report it with what the burner was doing: %s",
                status.phase,
                "https://github.com/stfnw-coding/wildflame-ha/issues",
            )
        return status

    async def async_set_power(self, on: bool) -> None:
        async with self._command_lock:
            status = await self._fresh_status()
            if status.powered == on:
                return
            if self._power_guard.active():
                raise _refused("power_command_pending")
            if on:
                if status.child_lock:
                    raise _refused("child_lock_active")
                if status.state is BurnerState.COOLING:
                    raise _refused("cooling_down")
                if status.state is BurnerState.FUEL_EMPTY:
                    raise _refused("fuel_empty")
                if status.state is BurnerState.UNKNOWN_PHASE:
                    raise _refused("unknown_phase", phase=str(status.phase))
            await self._send(CODE_POWER_TOGGLE)
            self._power_guard.start(status.powered)
        await self.async_request_refresh()

    async def async_set_child_lock(self, locked: bool) -> None:
        async with self._command_lock:
            status = await self._fresh_status()
            if status.child_lock == locked:
                return
            if self._child_lock_guard.active():
                raise _refused("child_lock_command_pending")
            await self._send(CODE_CHILD_LOCK_TOGGLE)
            self._child_lock_guard.start(status.child_lock)
        await self.async_request_refresh()

    async def async_set_flame_level(self, level: int) -> None:
        level = max(FLAME_MIN, min(FLAME_MAX, level))
        async with self._command_lock:
            status = await self._fresh_status()
            if status.state is not BurnerState.BURNING:
                raise _refused("not_burning")
            if status.child_lock:
                raise _refused("child_lock_active")
            # Step one at a time and publish the burner's own reading after every step,
            # so the slider follows the flame (5 -> 4 -> 3 ...) instead of jumping at the end.
            # Bounded so a burner that ignores a step cannot keep us looping.
            for _ in range(abs(level - status.flame_level) + 2):
                if status.flame_level == level or status.state is not BurnerState.BURNING:
                    break
                await self._send(CODE_FLAME_UP if level > status.flame_level else CODE_FLAME_DOWN)
                await asyncio.sleep(FLAME_STEP_DELAY_SECONDS)
                status = await self._fresh_status()

    async def _fresh_status(self) -> WildflameStatus:
        try:
            status = await self.client.get_status()
        except WildflameError as err:
            raise _error("cannot_connect", error=str(err)) from err
        self.async_set_updated_data(status)
        return status

    async def _send(self, code: str) -> None:
        try:
            await self.client.send_command(code)
        except WildflameError as err:
            raise _error("command_failed", error=str(err)) from err
