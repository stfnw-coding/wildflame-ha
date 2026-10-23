"""Diagnostics for the Wild Flame integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import WildflameConfigEntry

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WildflameConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    status = coordinator.data
    return {
        "entry": {"title": entry.title, "data": async_redact_data(entry.data, TO_REDACT)},
        "last_update_success": coordinator.last_update_success,
        "status": {
            "raw": {f"usart{idx}": value for idx, value in sorted(status.raw.items())},
            "state": status.state.value,
        }
        if status
        else None,
    }
