"""Child lock of the Wild Flame burner."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
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
    async_add_entities([WildflameChildLock(entry.runtime_data, "child_lock")])


class WildflameChildLock(WildflameEntity, LockEntity):
    @property
    def is_locked(self) -> bool:
        return self.coordinator.data.child_lock

    async def async_lock(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_child_lock(True)

    async def async_unlock(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_child_lock(False)
