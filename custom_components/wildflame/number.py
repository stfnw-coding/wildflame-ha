"""Flame level control for the Wild Flame burner."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import FLAME_MAX, FLAME_MIN, BurnerState
from .coordinator import WildflameConfigEntry
from .entity import WildflameEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WildflameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([WildflameFlameLevel(entry.runtime_data, "flame_level")])


class WildflameFlameLevel(WildflameEntity, NumberEntity):
    _attr_native_min_value = FLAME_MIN
    _attr_native_max_value = FLAME_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> int | None:
        status = self.coordinator.data
        if status.state is not BurnerState.BURNING:
            return None
        return status.flame_level

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_flame_level(round(value))
