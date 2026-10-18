"""Binary sensors for the Wild Flame burner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import WildflameStatus
from .coordinator import WildflameConfigEntry, WildflameCoordinator
from .entity import WildflameEntity


@dataclass(frozen=True, kw_only=True)
class WildflameBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[WildflameStatus], bool]


BINARY_SENSORS: tuple[WildflameBinarySensorDescription, ...] = (
    WildflameBinarySensorDescription(
        key="child_lock",
        device_class=BinarySensorDeviceClass.LOCK,
        # LOCK: on means unlocked, so invert the burner's "lock active" flag.
        value_fn=lambda s: not s.child_lock,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WildflameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        WildflameBinarySensor(entry.runtime_data, desc) for desc in BINARY_SENSORS
    )


class WildflameBinarySensor(WildflameEntity, BinarySensorEntity):
    entity_description: WildflameBinarySensorDescription

    def __init__(
        self,
        coordinator: WildflameCoordinator,
        description: WildflameBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)
