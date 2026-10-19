"""Tests for the Home Assistant entities and command safety."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.wildflame.api import (
    WildflameConnectionError,
    CODE_CHILD_LOCK_TOGGLE,
    CODE_FLAME_DOWN,
    CODE_FLAME_UP,
    CODE_POWER_TOGGLE,
)
from custom_components.wildflame.const import DOMAIN

SWITCH = "switch.haard"
FLAME = "number.haard_vlamhoogte"
STATUS = "sensor.haard_status"
CHILD_LOCK = "lock.haard_kinderslot"
ON_SINCE = "sensor.haard_laatst_aangezet"
AUTO_OFF = "number.haard_automatisch_uit_na"
FUEL_LOW = "binary_sensor.haard_brandstof_bijna_op"


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
    assert hass.states.get(CHILD_LOCK).state == "unlocked"
    assert hass.states.get(FLAME).state == "unavailable"  # only adjustable while burning
    assert hass.states.get(ON_SINCE).state == "unknown"
    assert hass.states.get(AUTO_OFF).state == "0.0"
    assert hass.states.get(FUEL_LOW).state == "off"


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


async def test_on_since(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    before = dt_util.utcnow()
    await call(hass, "switch", "turn_on", SWITCH)
    on_since = dt_util.parse_datetime(hass.states.get(ON_SINCE).state)
    assert on_since >= before.replace(microsecond=0)

    burner.ignite()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert dt_util.parse_datetime(hass.states.get(ON_SINCE).state) == on_since  # warming up counts

    await call(hass, "switch", "turn_off", SWITCH)
    assert dt_util.parse_datetime(hass.states.get(ON_SINCE).state) == on_since  # kept while off


async def test_on_since_restored_after_restart(hass: HomeAssistant, entry, burner, hass_storage) -> None:
    burner.powered, burner.phase, burner.flame = 1, 0, 5
    on_since = dt_util.utcnow() - timedelta(hours=2)
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {
            "auto_off_hours": 3,
            "powered_since": on_since.isoformat(),
            "last_seen": (dt_util.utcnow() - timedelta(minutes=1)).isoformat(),
        },
    }
    await setup(hass, entry)
    assert dt_util.parse_datetime(hass.states.get(ON_SINCE).state) == on_since.replace(microsecond=0)
    assert hass.states.get(AUTO_OFF).state == "3.0"


async def test_on_since_not_restored_after_long_gap(hass: HomeAssistant, entry, burner, hass_storage) -> None:
    burner.powered, burner.phase, burner.flame = 1, 0, 5
    old = dt_util.utcnow() - timedelta(days=2)
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {"auto_off_hours": 0, "powered_since": old.isoformat(), "last_seen": old.isoformat()},
    }
    await setup(hass, entry)
    assert dt_util.parse_datetime(hass.states.get(ON_SINCE).state) > old + timedelta(days=1)


async def test_last_switched_on_restored_while_off(hass: HomeAssistant, entry, burner, hass_storage) -> None:
    last_on = dt_util.utcnow() - timedelta(days=3)
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {"auto_off_hours": 0, "powered_since": None, "last_seen": None, "last_switched_on": last_on.isoformat()},
    }
    await setup(hass, entry)
    assert dt_util.parse_datetime(hass.states.get(ON_SINCE).state) == last_on.replace(microsecond=0)


async def test_auto_off(hass: HomeAssistant, entry, burner) -> None:
    burner.powered, burner.phase, burner.flame = 1, 0, 5
    await setup(hass, entry)
    await call(hass, "number", "set_value", AUTO_OFF, value=2)
    assert burner.commands == []  # just switched on

    coordinator = entry.runtime_data
    coordinator.powered_since = dt_util.utcnow() - timedelta(hours=2, minutes=1)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert burner.commands == [CODE_POWER_TOGGLE]
    assert hass.states.get(SWITCH).state == "off"

    # Off and cooling: nothing more is sent.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert burner.commands == [CODE_POWER_TOGGLE]


async def test_auto_off_disabled(hass: HomeAssistant, entry, burner) -> None:
    burner.powered, burner.phase, burner.flame = 1, 0, 5
    await setup(hass, entry)
    coordinator = entry.runtime_data
    coordinator.powered_since = dt_util.utcnow() - timedelta(hours=20)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert burner.commands == []


async def test_child_lock(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    await call(hass, "lock", "lock", CHILD_LOCK)
    assert burner.commands == [CODE_CHILD_LOCK_TOGGLE]
    assert hass.states.get(CHILD_LOCK).state == "locked"

    # Already locked: no toggle (that would unlock it).
    await call(hass, "lock", "lock", CHILD_LOCK)
    assert burner.commands == [CODE_CHILD_LOCK_TOGGLE]

    await call(hass, "lock", "unlock", CHILD_LOCK)
    assert burner.commands == [CODE_CHILD_LOCK_TOGGLE] * 2
    assert hass.states.get(CHILD_LOCK).state == "unlocked"


async def test_child_lock_guard_blocks_double_toggle(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    with patch.object(burner, "apply", side_effect=lambda code: burner.commands.append(code)):
        await call(hass, "lock", "lock", CHILD_LOCK)
        with pytest.raises(HomeAssistantError):
            await call(hass, "lock", "lock", CHILD_LOCK)
    assert burner.commands == [CODE_CHILD_LOCK_TOGGLE]


async def test_read_only_child_lock_removed(hass: HomeAssistant, entry, burner) -> None:
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_child_lock", config_entry=entry
    )
    await setup(hass, entry)
    assert registry.async_get(old.entity_id) is None


async def test_fuel_low(hass: HomeAssistant, entry, burner) -> None:
    burner.fuel = 1
    await setup(hass, entry)
    assert hass.states.get(FUEL_LOW).state == "on"
    # Not a "problem" sensor: that would show as OK/Problem instead of Bijna leeg/Voldoende.
    assert "device_class" not in hass.states.get(FUEL_LOW).attributes
    burner.fuel = 2
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(FUEL_LOW).state == "off"


async def test_unknown_phase_blocks_start(hass: HomeAssistant, entry, burner, caplog) -> None:
    burner.phase = 7
    await setup(hass, entry)
    assert hass.states.get(STATUS).state == "unknown_phase"
    assert "phase code 7" in caplog.text
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "switch", "turn_on", SWITCH)
    assert err.value.translation_key == "unknown_phase"
    assert burner.commands == []


async def test_refuse_start_while_cooling(hass: HomeAssistant, entry, burner) -> None:
    burner.phase = 1  # red LED: the burner cannot be started until cooling is done
    await setup(hass, entry)
    # A refusal because of the burner's state is not an error: no stack trace in the log.
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "switch", "turn_on", SWITCH)
    assert err.value.translation_key == "cooling_down"
    # Logs get the English text; the frontend shows the message in the user's language.
    assert "still cooling down" in str(err.value)
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


async def test_flame_slider_follows_each_step(hass: HomeAssistant, entry, burner) -> None:
    # One slide from 5 to 1 must show 4, 3, 2 and 1 as the burner reports them, not a jump at the end.
    burner.powered, burner.phase, burner.flame = 1, 0, 5
    await setup(hass, entry)
    seen: list[str] = []
    unsub = hass.bus.async_listen(
        "state_changed",
        lambda event: seen.append(event.data["new_state"].state)
        if event.data["entity_id"] == FLAME
        else None,
    )
    await call(hass, "number", "set_value", FLAME, value=1)
    unsub()
    assert seen == ["4", "3", "2", "1"]
    assert burner.commands == [CODE_FLAME_DOWN] * 4


async def test_flame_stops_when_burner_ignores_steps(hass: HomeAssistant, entry, burner) -> None:
    burner.powered, burner.phase, burner.flame = 1, 0, 5
    await setup(hass, entry)
    with patch.object(burner, "apply", side_effect=lambda code: burner.commands.append(code)):
        await call(hass, "number", "set_value", FLAME, value=1)
    assert len(burner.commands) == 6  # 4 steps + 2 retries, then gives up


async def test_flame_refused_when_not_burning(hass: HomeAssistant, entry, burner) -> None:
    burner.powered, burner.phase, burner.flame = 1, 10, 0  # igniter heating up
    await setup(hass, entry)
    assert hass.states.get(FLAME).state == "unavailable"
    with pytest.raises(HomeAssistantError) as err:
        await entry.runtime_data.async_set_flame_level(5)
    assert err.value.translation_key == "not_burning"
    assert burner.commands == []


async def test_unavailable_when_unreachable(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    await burner.stop()
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == "unavailable"


async def test_power_guard_expires(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    with (
        patch.object(burner, "apply", side_effect=lambda code: burner.commands.append(code)),
        patch("custom_components.wildflame.coordinator.POWER_TOGGLE_GUARD_SECONDS", -1),
    ):
        await call(hass, "switch", "turn_on", SWITCH)
        await call(hass, "switch", "turn_on", SWITCH)
    assert burner.commands == [CODE_POWER_TOGGLE] * 2


async def test_auto_off_failure_is_retried_later(hass: HomeAssistant, entry, burner, caplog) -> None:
    burner.powered, burner.phase, burner.flame = 1, 0, 5
    await setup(hass, entry)
    await call(hass, "number", "set_value", AUTO_OFF, value=1)
    coordinator = entry.runtime_data
    coordinator.powered_since = dt_util.utcnow() - timedelta(hours=2)
    with patch.object(
        coordinator.client, "send_command", side_effect=WildflameConnectionError("gone")
    ) as send:
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert "Automatic switch-off failed" in caplog.text
        # Within the retry interval no new attempt is made.
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert send.call_count == 1
    assert hass.states.get(SWITCH).state == "on"


async def test_flame_refused_with_child_lock(hass: HomeAssistant, entry, burner) -> None:
    burner.powered, burner.phase, burner.flame, burner.child_lock = 1, 0, 5, 1
    await setup(hass, entry)
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "number", "set_value", FLAME, value=3)
    assert err.value.translation_key == "child_lock_active"
    assert burner.commands == []


async def test_command_when_unreachable(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    await burner.stop()
    with pytest.raises(HomeAssistantError) as err:
        await entry.runtime_data.async_set_power(True)
    assert not isinstance(err.value, ServiceValidationError)
    assert err.value.translation_key == "cannot_connect"


async def test_command_failed(hass: HomeAssistant, entry, burner) -> None:
    await setup(hass, entry)
    with (
        patch.object(
            entry.runtime_data.client, "send_command", side_effect=WildflameConnectionError("gone")
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await call(hass, "switch", "turn_on", SWITCH)
    assert err.value.translation_key == "command_failed"


async def test_unload_and_remove(hass: HomeAssistant, entry, burner, hass_storage) -> None:
    await setup(hass, entry)
    await call(hass, "number", "set_value", AUTO_OFF, value=1)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{entry.entry_id}" in hass_storage

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass.states.get(SWITCH).state == "unavailable"

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage
