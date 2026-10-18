"""Sensors for the Wild Flame burner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import BurnerState, WildflameStatus
from .coordinator import WildflameConfigEntry, WildflameCoordinator
from .entity import WildflameEntity


@dataclass(frozen=True, kw_only=True)
class WildflameSensorDescription(SensorEntityDescription):
    value_fn: Callable[[WildflameStatus], float | str | None]


SENSORS: tuple[WildflameSensorDescription, ...] = (
    WildflameSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[s.value for s in BurnerState],
        value_fn=lambda s: s.state.value,
    ),
    WildflameSensorDescription(
        key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.fuel_percent,
    ),
    WildflameSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.temperature,
    ),
    WildflameSensorDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.humidity,
    ),
    # Raw phase code, kept visible so unknown codes (e.g. errors) show up in history.
    WildflameSensorDescription(
        key="phase",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.phase,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WildflameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(
                (WildflameStatusSensor if desc.key == "status" else WildflameSensor)(coordinator, desc)
                for desc in SENSORS
            ),
            WildflameOnSinceSensor(coordinator, "on_since"),
        ]
    )


class WildflameSensor(WildflameEntity, SensorEntity):
    entity_description: WildflameSensorDescription

    def __init__(
        self, coordinator: WildflameCoordinator, description: WildflameSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        return self.entity_description.value_fn(self.coordinator.data)


class WildflameStatusSensor(WildflameSensor):
    """Status with the time it was entered, e.g. to show how long the burner has been warming up."""

    _since: datetime | None = None
    _last: str | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        value = self.native_value
        if value != self._last:
            self._last, self._since = value, dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._last, self._since = self.native_value, dt_util.utcnow()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"since": self._since.isoformat() if self._since else None}


class WildflameOnSinceSensor(WildflameEntity, SensorEntity):
    """When the burner was switched on; empty while it is off. Survives a restart."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.powered_since
