"""The Wild Flame bio-ethanol burner integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store

from .api import WildflameClient
from .const import CONF_WIFI_INTERFACE, DOMAIN
from .coordinator import WildflameConfigEntry, WildflameCoordinator
from .wifi import (
    WifiSignalCoordinator,
    async_find_wifi_link,
    async_start_wifi_watchdog,
    async_stop_wifi_watchdog,
)

PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: WildflameConfigEntry) -> bool:
    # Own session: the burner closes every connection, so pooled keep-alive connections are useless.
    session = async_create_clientsession(hass, auto_cleanup=True)
    client = WildflameClient(session, entry.data[CONF_HOST])
    # Before the first refresh: while the Wi-Fi link is down, setup keeps failing until it is restored.
    async_start_wifi_watchdog(hass, entry)
    coordinator = WildflameCoordinator(hass, entry, client)
    _remove_old_entities(hass, entry)
    await _remove_old_storage(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.wifi_signal = await _async_wifi_signal(hass, entry)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WildflameConfigEntry) -> bool:
    # The Wi-Fi watchdog keeps running across reloads; it stops itself once the entry is disabled.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: WildflameConfigEntry) -> None:
    async_stop_wifi_watchdog(hass, entry.entry_id)


async def _async_wifi_signal(
    hass: HomeAssistant, entry: WildflameConfigEntry
) -> WifiSignalCoordinator | None:
    """Follows the Wi-Fi signal if Home Assistant OS reaches the burner over its own Wi-Fi interface."""
    if not (interface := entry.data.get(CONF_WIFI_INTERFACE)):
        if not (link := await async_find_wifi_link(hass, entry.data[CONF_HOST])):
            return None
        interface = link.interface
    wifi_signal = WifiSignalCoordinator(hass, entry, interface)
    # Not a first refresh: without an answer from the Supervisor the burner still works.
    await wifi_signal.async_refresh()
    return wifi_signal


# Entities from earlier versions that no longer exist.
_OLD_ENTITIES: tuple[tuple[Platform, str], ...] = (
    # 0.1.x showed the child lock as a binary sensor; it is a lock entity since 0.2.0.
    (Platform.BINARY_SENSOR, "child_lock"),
    # The auto-off time was removed in 0.4.0; an automation does the same.
    (Platform.NUMBER, "auto_off"),
    # "Last switched on" was removed in 0.5.0: it was not burner data but derived from the switch,
    # whose history Home Assistant already keeps.
    (Platform.SENSOR, "on_since"),
    # "Fuel low" was removed in 0.6.0: an automation on the fuel level does the same.
    (Platform.BINARY_SENSOR, "fuel_low"),
)


def _remove_old_entities(hass: HomeAssistant, entry: WildflameConfigEntry) -> None:
    registry = er.async_get(hass)
    for platform, key in _OLD_ENTITIES:
        if entity_id := registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}"):
            registry.async_remove(entity_id)


async def _remove_old_storage(hass: HomeAssistant, entry: WildflameConfigEntry) -> None:
    """Up to 0.4.0 the integration kept its own storage file; nothing is stored any more."""
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
