"""The Wild Flame bio-ethanol burner integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store

from .api import WildflameClient
from .const import DOMAIN, STORAGE_VERSION
from .coordinator import WildflameConfigEntry, WildflameCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: WildflameConfigEntry) -> bool:
    # Own session: the burner closes every connection, so pooled keep-alive connections are useless.
    session = async_create_clientsession(hass, auto_cleanup=True)
    client = WildflameClient(session, entry.data[CONF_HOST])
    coordinator = WildflameCoordinator(hass, entry, client)
    _remove_old_entities(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WildflameConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: WildflameConfigEntry) -> None:
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


# Entities from earlier versions that no longer exist.
_OLD_ENTITIES: tuple[tuple[Platform, str], ...] = (
    # 0.1.x showed the child lock as a binary sensor; it is a lock entity since 0.2.0.
    (Platform.BINARY_SENSOR, "child_lock"),
    # The auto-off time was removed in 0.4.0; an automation does the same.
    (Platform.NUMBER, "auto_off"),
)


def _remove_old_entities(hass: HomeAssistant, entry: WildflameConfigEntry) -> None:
    registry = er.async_get(hass)
    for platform, key in _OLD_ENTITIES:
        if entity_id := registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}"):
            registry.async_remove(entity_id)
