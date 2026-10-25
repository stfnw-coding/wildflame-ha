"""Sensors for the Wild Flame burner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import BurnerState, WildflameStatus
from .coordinator import WildflameConfigEntry, WildflameCoordinator
from .entity import WildflameEntity
from .wifi import WifiSignalCoordinator

# Data comes from the coordinator.
PARALLEL_UPDATES = 0


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
    sensors: list[SensorEntity] = [WildflameSensor(coordinator, desc) for desc in SENSORS]
    if coordinator.wifi_signal:
        sensors.append(WildflameWifiSignalSensor(coordinator.wifi_signal, "wifi_signal"))
    async_add_entities(sensors)


class WildflameSensor(WildflameEntity, SensorEntity):
    entity_description: WildflameSensorDescription

    def __init__(
        self, coordinator: WildflameCoordinator, description: WildflameSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> float | str | None:
        return self.entity_description.value_fn(self.coordinator.data)


class WildflameWifiSignalSensor(WildflameEntity[WifiSignalCoordinator], SensorEntity):
    """Strength of Home Assistant's Wi-Fi connection to the burner. Unknown while not connected.

    No signal strength device class: that one needs dB or dBm, and NetworkManager reports %.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    @override
    def native_value(self) -> int | None:
        return self.coordinator.data
