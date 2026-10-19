"""Power switch for the Wild Flame burner."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WildflameConfigEntry
from .entity import WildflameEntity

# The coordinator serialises all commands to the burner itself.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WildflameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([WildflamePowerSwitch(entry.runtime_data, "power")])


class WildflamePowerSwitch(WildflameEntity, SwitchEntity):
    _attr_name = None  # main feature: entity takes the device name

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.powered

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(False)
