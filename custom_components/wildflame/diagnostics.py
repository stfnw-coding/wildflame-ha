"""Diagnostics for the Wild Flame integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import WildflameConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WildflameConfigEntry
) -> dict[str, Any]:
    # Nothing to redact: the only setting is the burner's address on its own Wi-Fi.
    coordinator = entry.runtime_data
    status = coordinator.data
    return {
        "entry": {"title": entry.title, "data": dict(entry.data)},
        "last_update_success": coordinator.last_update_success,
        "status": {
            "raw": {f"usart{idx}": value for idx, value in sorted(status.raw.items())},
            "state": status.state.value,
        }
        if status
        else None,
        "powered_since": coordinator.powered_since,
        "last_switched_on": coordinator.last_switched_on,
        "auto_off_hours": coordinator.auto_off_hours,
    }
