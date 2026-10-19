"""Polling coordinator and command logic for the Wild Flame burner."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import time
from typing import Any, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    CODE_CHILD_LOCK_TOGGLE,
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
from .const import (
    AUTO_OFF_RETRY_SECONDS,
    DOMAIN,
    FLAME_STEP_DELAY_SECONDS,
    POWER_TOGGLE_GUARD_SECONDS,
    POWERED_SINCE_MAX_GAP,
    SCAN_INTERVAL,
    STORAGE_SAVE_INTERVAL_SECONDS,
    STORAGE_VERSION,
)

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
        self, hass: HomeAssistant, entry: WildflameConfigEntry, client: WildflameClient
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
        self._command_lock = asyncio.Lock()
        self._power_guard = _ToggleGuard()
        self._child_lock_guard = _ToggleGuard()
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.powered_since: datetime | None = None
        # Unlike powered_since this is kept after switching off, so it never goes blank.
        self.last_switched_on: datetime | None = None
        self.auto_off_hours: float = 0
        self._auto_off_attempt: float | None = None
        self._last_save = 0.0
        self._warned_phases: set[int] = set()

    @override
    async def _async_setup(self) -> None:
        stored = await self._store.async_load() or {}
        self.auto_off_hours = float(stored.get("auto_off_hours", 0))
        self.last_switched_on = dt_util.parse_datetime(
            stored.get("last_switched_on") or stored.get("powered_since") or ""
        )
        # Only trust the stored start time if Home Assistant saw the burner burning just before
        # it went down; otherwise it may have been switched off and on again in between.
        last_seen = dt_util.parse_datetime(stored.get("last_seen") or "")
        if last_seen and dt_util.utcnow() - last_seen < POWERED_SINCE_MAX_GAP:
            self.powered_since = dt_util.parse_datetime(stored.get("powered_since") or "")

    @override
    async def _async_update_data(self) -> WildflameStatus:
        try:
            status = await self.client.get_status()
        except WildflameError as err:
            raise UpdateFailed(str(err)) from err
        self._power_guard.observe(status.powered)
        self._child_lock_guard.observe(status.child_lock)
        self._track_powered(status)
        self._check_auto_off(status)
        if status.state is BurnerState.UNKNOWN_PHASE and status.phase not in self._warned_phases:
            self._warned_phases.add(status.phase)
            _LOGGER.warning(
                "The burner reports phase code %s, which this integration does not know yet. "
                "Please report it with what the burner was doing: %s",
                status.phase,
                "https://github.com/stfnw-coding/wildflame-ha/issues",
            )
        return status

    def _track_powered(self, status: WildflameStatus) -> None:
        if status.powered:
            if self.powered_since is None:
                self.powered_since = self.last_switched_on = dt_util.utcnow()
                self._save()
            elif time.monotonic() - self._last_save > STORAGE_SAVE_INTERVAL_SECONDS:
                self._save()  # refreshes last_seen
        elif self.powered_since is not None:
            self.powered_since = None
            self._auto_off_attempt = None
            self._save()

    def _save(self) -> None:
        self._last_save = time.monotonic()
        self._store.async_delay_save(self._storage_data, 0)

    def _storage_data(self) -> dict[str, Any]:
        return {
            "auto_off_hours": self.auto_off_hours,
            "powered_since": self.powered_since.isoformat() if self.powered_since else None,
            "last_seen": dt_util.utcnow().isoformat() if self.powered_since else None,
            "last_switched_on": self.last_switched_on.isoformat() if self.last_switched_on else None,
        }

    async def async_set_auto_off_hours(self, hours: float) -> None:
        self.auto_off_hours = hours
        self._save()
        if self.data is not None:
            self._check_auto_off(self.data)
        self.async_update_listeners()

    def _check_auto_off(self, status: WildflameStatus) -> None:
        if not (status.powered and self.auto_off_hours and self.powered_since):
            return
        if dt_util.utcnow() - self.powered_since < timedelta(hours=self.auto_off_hours):
            return
        if (
            self._auto_off_attempt is not None
            and time.monotonic() - self._auto_off_attempt < AUTO_OFF_RETRY_SECONDS
        ):
            return
        self._auto_off_attempt = time.monotonic()
        self.config_entry.async_create_task(
            self.hass, self._async_auto_off(), f"{DOMAIN} auto off"
        )

    async def _async_auto_off(self) -> None:
        _LOGGER.info("Switching the burner off: the %s h auto-off time has passed", self.auto_off_hours)
        try:
            await self.async_set_power(False)
        except HomeAssistantError as err:
            _LOGGER.warning("Automatic switch-off failed, will retry: %s", err)

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
