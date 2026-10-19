"""Flame level of the Wild Flame burner."""

from __future__ import annotations

from typing import override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import FLAME_MAX, FLAME_MIN, BurnerState
from .coordinator import WildflameConfigEntry
from .entity import WildflameEntity

# The coordinator serialises all commands to the burner itself.
PARALLEL_UPDATES = 0


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
    @override
    def available(self) -> bool:
        # Greyed out unless the flame can actually be adjusted.
        return super().available and self.coordinator.data.state is BurnerState.BURNING

    @property
    @override
    def native_value(self) -> int:
        return self.coordinator.data.flame_level

    @override
    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_flame_level(round(value))
