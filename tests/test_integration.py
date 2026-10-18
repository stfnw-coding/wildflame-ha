"""Tests for the Home Assistant entities and command safety."""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.wildflame.api import CODE_FLAME_DOWN, CODE_FLAME_UP, CODE_POWER_TOGGLE

SWITCH = "switch.haard"
FLAME = "number.haard_vlamhoogte"
STATUS = "sensor.haard_status"


@pytest.fixture(autouse=True)
def fast_steps():
    with patch("custom_components.wildflame.coordinator.FLAME_STEP_DELAY_SECONDS", 0):
        yield


async def setup(hass: HomeAssistant, entry) -> None:
    hass.config.language = "nl"  # entity ids follow the system language, as in the real install
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    await hass.async_block_till_done()


async def test_entities_created(hass: HomeAssistant, entry, burner) -> None:
    burner.phase = 1
    await setup(hass, entry)
    assert hass.states.get(SWITCH).state == "off"
    assert hass.states.get(STATUS).state == "cooling"
    assert hass.states.get("sensor.haard_fasecode").state == "1"
    assert hass.states.get("sensor.haard_brandstofniveau").state == "20"
    assert hass.states.get("sensor.haard_kamertemperatuur").state == "20.0"
    assert hass.states.get("sensor.haard_luchtvochtigheid").state == "45.0"
    assert hass.states.get("binary_sensor.haard_kinderslot").state == "on"  # on = unlocked
    assert hass.states.get(FLAME).state == "unknown"


async def test_turn_on_and_off(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    await call(hass, "switch", "turn_on", SWITCH)
    assert burner.commands == [CODE_POWER_TOGGLE]
    assert hass.states.get(STATUS).state == "warming_up"
    warming_since = hass.states.get(STATUS).attributes["since"]
    assert warming_since is not None

    # Already on: turning on again must NOT send another toggle (that would switch it off).
    await call(hass, "switch", "turn_on", SWITCH)
    assert burner.commands == [CODE_POWER_TOGGLE]

    burner.ignite()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "burning"
    assert hass.states.get(STATUS).attributes["since"] > warming_since
    await call(hass, "switch", "turn_off", SWITCH)
    assert burner.commands == [CODE_POWER_TOGGLE, CODE_POWER_TOGGLE]
    assert hass.states.get(STATUS).state == "cooling"

    # Already off: no toggle.
    await call(hass, "switch", "turn_off", SWITCH)
    assert len(burner.commands) == 2


async def test_refuse_start_while_cooling(hass: HomeAssistant, entry, burner) -> None:
    burner.phase = 1  # red LED: the burner cannot be started until cooling is done
    await setup(hass, entry)
    with pytest.raises(HomeAssistantError):
        await call(hass, "switch", "turn_on", SWITCH)
    assert burner.commands == []


async def test_start_allowed_when_ready(hass: HomeAssistant, entry, burner) -> None:
    burner.phase = 6  # LED off
    await setup(hass, entry)
    await call(hass, "switch", "turn_on", SWITCH)
    assert burner.commands == [CODE_POWER_TOGGLE]


async def test_refuse_start_with_child_lock(hass: HomeAssistant, entry, burner) -> None:
    burner.child_lock = 1
    await setup(hass, entry)
    with pytest.raises(HomeAssistantError):
        await call(hass, "switch", "turn_on", SWITCH)
    assert burner.commands == []


async def test_power_guard_blocks_double_toggle(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    # Burner ignores the toggle (e.g. still busy): state stays off.
    with patch.object(burner, "apply", side_effect=lambda code: burner.commands.append(code)):
        await call(hass, "switch", "turn_on", SWITCH)
        with pytest.raises(HomeAssistantError):
            await call(hass, "switch", "turn_on", SWITCH)
    assert burner.commands == [CODE_POWER_TOGGLE]


async def test_flame_level_steps(hass: HomeAssistant, entry, burner) -> None:
    burner.powered, burner.phase, burner.flame = 1, 0, 2
    await setup(hass, entry)
    assert hass.states.get(FLAME).state == "2"

    await call(hass, "number", "set_value", FLAME, value=5)
    assert burner.commands == [CODE_FLAME_UP] * 3
    assert hass.states.get(FLAME).state == "5"

    await call(hass, "number", "set_value", FLAME, value=4)
    assert burner.commands[-1] == CODE_FLAME_DOWN
    assert burner.flame == 4


async def test_flame_refused_when_not_burning(hass: HomeAssistant, entry, burner) -> None:
    burner.powered, burner.phase, burner.flame = 1, 10, 0  # igniter heating up
    await setup(hass, entry)
    with pytest.raises(HomeAssistantError):
        await call(hass, "number", "set_value", FLAME, value=5)
    assert burner.commands == []


async def test_unavailable_when_unreachable(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    await burner.stop()
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == "unavailable"
