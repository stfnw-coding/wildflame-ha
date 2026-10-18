"""Flame level and auto-off time for the Wild Flame burner."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import FLAME_MAX, FLAME_MIN, BurnerState
from .const import AUTO_OFF_MAX_HOURS
from .coordinator import WildflameConfigEntry
from .entity import WildflameEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WildflameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            WildflameFlameLevel(entry.runtime_data, "flame_level"),
            WildflameAutoOff(entry.runtime_data, "auto_off"),
        ]
    )


class WildflameFlameLevel(WildflameEntity, NumberEntity):
    _attr_native_min_value = FLAME_MIN
    _attr_native_max_value = FLAME_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    @property
    def available(self) -> bool:
        # Greyed out unless the flame can actually be adjusted.
        return super().available and self.coordinator.data.state is BurnerState.BURNING

    @property
    def native_value(self) -> int:
        return self.coordinator.data.flame_level

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_flame_level(round(value))


class WildflameAutoOff(WildflameEntity, NumberEntity):
    """Switch the burner off after it has been on this long; 0 means never."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_native_min_value = 0
    _attr_native_max_value = AUTO_OFF_MAX_HOURS
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return self.coordinator.auto_off_hours

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_auto_off_hours(value)
