"""Tests for the diagnostics download."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from .test_integration import setup


async def test_diagnostics(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, entry, burner
) -> None:
    burner.powered, burner.phase, burner.flame = 1, 0, 5
    await setup(hass, entry)
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diagnostics["entry"] == {"title": "Haard", "data": {"host": burner.host}}
    assert diagnostics["last_update_success"] is True
    assert diagnostics["status"] == {
        "raw": {
            "usart1": 2.0,
            "usart2": 0.0,
            "usart3": 5.0,
            "usart4": 45.0,
            "usart5": 20.0,
            "usart6": 0.0,
            "usart7": 1.0,
        },
        "state": "burning",
    }
    assert diagnostics["powered_since"] is not None
    assert diagnostics["auto_off_hours"] == 0
