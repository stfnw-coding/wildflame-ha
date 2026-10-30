"""Tests for reconnecting Home Assistant OS to the burner's Wi-Fi."""

from datetime import timedelta
from ipaddress import ip_interface
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohasupervisor import SupervisorError
from aiohasupervisor.models import InterfaceType
from homeassistant.components.hassio.const import DATA_COMPONENT
from homeassistant.components.hassio.handler import HassioAPIError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER, ConfigEntryDisabler, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.wildflame.const import (
    CONF_WIFI_INTERFACE,
    CONF_WIFI_SSID,
    DOMAIN,
    WIFI_CHECK_INTERVAL_SECONDS,
)
from custom_components.wildflame.wifi import WifiLink, async_find_wifi_link, async_start_wifi_watchdog

from .test_integration import setup

WIFI_SIGNAL = "sensor.haard_wifi_signaal"

SSID = "WILDFLAME800"
PASSWORD = "burner-secret"


def interface(name, kind, address, ssid=None, connected=True, signal=72):
    return SimpleNamespace(
        interface=name,
        type=kind,
        connected=connected,
        ipv4=SimpleNamespace(address=[ip_interface(address)]) if address else None,
        wifi=SimpleNamespace(ssid=ssid, signal=signal) if ssid else None,
    )


ETHERNET = interface("end0", InterfaceType.ETHERNET, "192.168.1.99/24")
WLAN = interface("wlan0", InterfaceType.WIRELESS, "192.168.4.10/24", SSID)


@pytest.fixture
def supervisor(hass: HomeAssistant):
    """A Supervisor with Ethernet to the home network and Wi-Fi to the burner."""
    client = MagicMock()
    client.network.info = AsyncMock(return_value=SimpleNamespace(interfaces=[ETHERNET, WLAN]))
    client.network.interface_info = AsyncMock(return_value=WLAN)
    client.network.access_points = AsyncMock(return_value=[SimpleNamespace(ssid=SSID)])
    hassio = MagicMock()
    hassio.send_command = AsyncMock(return_value={"result": "ok"})
    hass.data[DATA_COMPONENT] = hassio
    with (
        patch("custom_components.wildflame.wifi.is_hassio", return_value=True),
        patch("custom_components.wildflame.wifi.get_supervisor_client", return_value=client),
    ):
        yield SimpleNamespace(client=client, send_command=hassio.send_command)


def wifi_entry(host: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Haard",
        unique_id=host,
        data={
            CONF_HOST: host,
            CONF_PASSWORD: PASSWORD,
            CONF_WIFI_INTERFACE: "wlan0",
            CONF_WIFI_SSID: SSID,
        },
    )


def lose_wifi(supervisor) -> None:
    supervisor.client.network.interface_info.return_value = interface(
        "wlan0", InterfaceType.WIRELESS, None, connected=False
    )


async def test_find_wifi_link(hass: HomeAssistant, supervisor) -> None:
    assert await async_find_wifi_link(hass, "192.168.4.1") == WifiLink("wlan0", SSID)
    # The burner is not on a Wi-Fi interface.
    assert await async_find_wifi_link(hass, "192.168.1.50") is None
    assert await async_find_wifi_link(hass, "10.0.0.1") is None
    assert await async_find_wifi_link(hass, "burner.local") is None
    supervisor.client.network.info.side_effect = SupervisorError
    assert await async_find_wifi_link(hass, "192.168.4.1") is None


async def test_find_wifi_link_without_supervisor(hass: HomeAssistant) -> None:
    assert await async_find_wifi_link(hass, "192.168.4.1") is None


@pytest.fixture
def tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    """Let time pass one check interval at a time, waiting for each Wi-Fi check to finish."""

    async def tick(checks: int = 1) -> None:
        for _ in range(checks):
            freezer.tick(timedelta(seconds=WIFI_CHECK_INTERVAL_SECONDS))
            async_fire_time_changed(hass)
            await hass.async_block_till_done(wait_background_tasks=True)

    return tick


def watched_entry(hass: HomeAssistant, host: str = "192.168.4.1") -> MockConfigEntry:
    entry = wifi_entry(host)
    entry.add_to_hass(hass)
    async_start_wifi_watchdog(hass, entry)
    return entry


async def test_reconnects_when_wifi_gave_up(hass: HomeAssistant, supervisor, tick) -> None:
    watched_entry(hass)
    lose_wifi(supervisor)
    # The first check gives NetworkManager a minute to reconnect by itself.
    await tick()
    supervisor.send_command.assert_not_awaited()
    await tick()
    supervisor.send_command.assert_awaited_once()
    command, kwargs = supervisor.send_command.await_args.args[0], supervisor.send_command.await_args.kwargs
    assert command == "/network/interface/wlan0/update"
    assert kwargs["payload"] == {
        "enabled": True,
        "ipv4": {"method": "auto"},
        "wifi": {"mode": "infrastructure", "auth": "wpa-psk", "ssid": SSID, "psk": PASSWORD},
    }


async def test_leaves_working_wifi_alone(hass: HomeAssistant, supervisor, tick) -> None:
    watched_entry(hass)
    await tick(3)
    assert supervisor.client.network.interface_info.await_count == 3
    supervisor.client.network.access_points.assert_not_awaited()
    supervisor.send_command.assert_not_awaited()


async def test_leaves_a_brief_drop_to_networkmanager(hass: HomeAssistant, supervisor, tick) -> None:
    watched_entry(hass)
    lose_wifi(supervisor)
    await tick()
    supervisor.client.network.interface_info.return_value = WLAN
    await tick()
    lose_wifi(supervisor)
    await tick()
    supervisor.send_command.assert_not_awaited()


async def test_waits_for_burner_wifi_on_the_air(hass: HomeAssistant, supervisor, tick) -> None:
    watched_entry(hass)
    lose_wifi(supervisor)
    supervisor.client.network.access_points.return_value = [SimpleNamespace(ssid="Neighbours")]
    await tick(3)
    supervisor.send_command.assert_not_awaited()
    supervisor.client.network.access_points.return_value = [SimpleNamespace(ssid=SSID)]
    await tick()
    supervisor.send_command.assert_awaited_once()


async def test_retries_every_2_minutes_then_every_30(hass: HomeAssistant, supervisor, tick) -> None:
    watched_entry(hass)
    lose_wifi(supervisor)
    await tick(2)
    assert supervisor.send_command.await_count == 1
    # The burner turned the reconnect away: try again 2 minutes later, 10 times in all.
    for tries in range(2, 11):
        await tick()
        assert supervisor.send_command.await_count == tries - 1
        await tick()
        assert supervisor.send_command.await_count == tries
    # Then every 30 minutes: a wrong password, say, should not add a profile every 2 minutes.
    await tick(29)
    assert supervisor.send_command.await_count == 10
    await tick()
    assert supervisor.send_command.await_count == 11
    await tick(30)
    assert supervisor.send_command.await_count == 12

    # Once the Wi-Fi worked again, a next loss is handled quickly again.
    supervisor.client.network.interface_info.return_value = WLAN
    await tick()
    lose_wifi(supervisor)
    await tick(2)
    assert supervisor.send_command.await_count == 13


async def test_connecting_does_not_reset_the_retries(hass: HomeAssistant, supervisor, tick) -> None:
    watched_entry(hass)
    lose_wifi(supervisor)
    await tick(2)
    # NetworkManager tries the settings (a wrong password, say) and fails again, 10 times.
    connecting = interface("wlan0", InterfaceType.WIRELESS, None, connected=True)
    for _ in range(9):
        supervisor.client.network.interface_info.return_value = connecting
        await tick()
        lose_wifi(supervisor)
        await tick(2)
    assert supervisor.send_command.await_count == 10
    # Without an address the connection never worked: now 30 minutes until the next try.
    await tick(29)
    assert supervisor.send_command.await_count == 10
    await tick()
    assert supervisor.send_command.await_count == 11


@pytest.mark.parametrize("error", [SupervisorError("busy"), HassioAPIError()])
async def test_reconnect_failure_is_logged(
    hass: HomeAssistant, supervisor, tick, caplog: pytest.LogCaptureFixture, error
) -> None:
    watched_entry(hass)
    lose_wifi(supervisor)
    supervisor.send_command.side_effect = error
    await tick(2)
    assert "Could not restore the Wi-Fi connection to the burner" in caplog.text
    # The next check still runs.
    await tick()
    assert supervisor.client.network.interface_info.await_count == 3


async def test_reconnects_while_setup_retries(hass: HomeAssistant, supervisor, burner, tick) -> None:
    """The Wi-Fi went down and Home Assistant restarted: setup keeps failing until the link is back."""
    await burner.stop()
    entry = wifi_entry(burner.host)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    # Retries wait up to 10 minutes; leave out Home Assistant's next one.
    entry.async_cancel_retry_setup()

    lose_wifi(supervisor)
    await tick()
    await burner.start()
    await tick()
    supervisor.send_command.assert_awaited_once()
    # Set up right away after the reconnect.
    assert entry.state is ConfigEntryState.LOADED


async def test_unreachable_burner_on_working_wifi(hass: HomeAssistant, supervisor, burner, tick) -> None:
    """A burner that skips answers for a minute or two is left alone."""
    entry = wifi_entry(burner.host)
    await setup(hass, entry)
    await burner.stop()
    await tick(2)
    await burner.start()
    await tick(3)
    supervisor.client.network.access_points.assert_not_awaited()
    supervisor.send_command.assert_not_awaited()


async def test_reconnects_a_stuck_link(
    hass: HomeAssistant, supervisor, burner, tick, caplog: pytest.LogCaptureFixture
) -> None:
    """The interface stays connected with an address, but the burner stops answering until the Wi-Fi reconnects."""
    entry = wifi_entry(burner.host)
    await setup(hass, entry)
    await burner.stop()
    # The first failed poll is at the first tick; 3 minutes after it the link counts as stuck.
    await tick(3)
    supervisor.send_command.assert_not_awaited()
    await tick()
    supervisor.send_command.assert_awaited_once()
    assert supervisor.send_command.await_args.args[0] == "/network/interface/wlan0/update"
    assert "is up, but the burner has not answered for 3 minutes; reconnecting" in caplog.text

    # Still silent after reconnecting: the connected interface does not reset the retries, so the next try
    # comes 2 minutes later instead of every minute.
    await tick()
    assert supervisor.send_command.await_count == 1
    await tick()
    assert supervisor.send_command.await_count == 2

    # Once the burner answers again, the link is left alone.
    await burner.start()
    await tick(5)
    assert supervisor.send_command.await_count == 2
    assert entry.state is ConfigEntryState.LOADED


async def test_stuck_link_while_setup_retries(hass: HomeAssistant, supervisor, burner, tick) -> None:
    """Home Assistant restarted while the link was stuck: failed setup attempts count as no answer."""
    await burner.stop()
    entry = wifi_entry(burner.host)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    entry.async_cancel_retry_setup()
    # 3 minutes after the failed setup the Wi-Fi reconnects, and setup is tried again right away.
    await tick(2)
    supervisor.send_command.assert_not_awaited()
    await burner.start()
    await tick()
    supervisor.send_command.assert_awaited_once()
    assert entry.state is ConfigEntryState.LOADED


async def test_stuck_link_burner_not_on_the_air(hass: HomeAssistant, supervisor, burner, tick) -> None:
    entry = wifi_entry(burner.host)
    await setup(hass, entry)
    await burner.stop()
    supervisor.client.network.access_points.return_value = [SimpleNamespace(ssid="Neighbours")]
    await tick(5)
    supervisor.send_command.assert_not_awaited()


async def test_no_stuck_link_without_reports(hass: HomeAssistant, supervisor, tick) -> None:
    """Without polls (polling disabled, say) nothing says the burner is silent: a connected link is left alone."""
    watched_entry(hass)
    await tick(10)
    supervisor.send_command.assert_not_awaited()


async def test_survives_a_reload(hass: HomeAssistant, supervisor, burner, tick) -> None:
    entry = wifi_entry(burner.host)
    await setup(hass, entry)
    lose_wifi(supervisor)
    await tick()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await tick()
    supervisor.send_command.assert_awaited_once()


async def test_no_watchdog_without_password(hass: HomeAssistant, supervisor, entry, tick) -> None:
    await setup(hass, entry)
    lose_wifi(supervisor)
    await tick(3)
    supervisor.client.network.interface_info.assert_not_awaited()


async def test_stops_when_entry_removed(hass: HomeAssistant, supervisor, burner, tick) -> None:
    entry = wifi_entry(burner.host)
    await setup(hass, entry)
    supervisor.client.network.interface_info.reset_mock()
    await hass.config_entries.async_remove(entry.entry_id)
    await tick(2)
    supervisor.client.network.interface_info.assert_not_awaited()


async def test_stops_when_entry_disabled(hass: HomeAssistant, supervisor, burner, tick) -> None:
    await burner.stop()
    entry = wifi_entry(burner.host)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    # Not loaded, so Home Assistant does not unload it: the watchdog notices by itself.
    await hass.config_entries.async_set_disabled_by(entry.entry_id, ConfigEntryDisabler.USER)
    await tick(2)
    supervisor.client.network.interface_info.assert_not_awaited()


async def test_user_flow_with_password(hass: HomeAssistant, burner) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    # The fake burner's address has a port in it; finding the interface is tested above.
    with patch(
        "custom_components.wildflame.config_flow.async_find_wifi_link",
        return_value=WifiLink("wlan0", SSID),
    ) as find:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: burner.host, CONF_PASSWORD: PASSWORD}
        )
    find.assert_awaited_once_with(hass, burner.host)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_HOST: burner.host,
        CONF_PASSWORD: PASSWORD,
        CONF_WIFI_INTERFACE: "wlan0",
        CONF_WIFI_SSID: SSID,
    }


async def test_user_flow_password_without_wifi(hass: HomeAssistant, burner) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: burner.host, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PASSWORD: "wifi_not_found"}

    # Without the password the burner can still be added.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: burner.host})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: burner.host}


async def test_reconfigure_removes_password(hass: HomeAssistant, supervisor, burner, tick) -> None:
    entry = wifi_entry(burner.host)
    await setup(hass, entry)
    supervisor.client.network.interface_info.reset_mock()
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: burner.host})
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_HOST: burner.host}
    # Without the password the Wi-Fi is no longer watched.
    await tick(2)
    supervisor.client.network.interface_info.assert_not_awaited()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_diagnostics_redacts_password(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, supervisor, burner
) -> None:
    entry = wifi_entry(burner.host)
    await setup(hass, entry)
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diagnostics["entry"]["data"] == {
        CONF_HOST: burner.host,
        CONF_PASSWORD: "**REDACTED**",
        CONF_WIFI_INTERFACE: "wlan0",
        CONF_WIFI_SSID: SSID,
    }
    assert diagnostics["wifi_signal"] == {"interface": "wlan0", "signal": 72}


async def test_wifi_signal_sensor(hass: HomeAssistant, supervisor, burner, tick) -> None:
    await setup(hass, wifi_entry(burner.host))
    state = hass.states.get(WIFI_SIGNAL)
    assert state.state == "72"
    assert state.attributes["unit_of_measurement"] == "%"
    assert er.async_get(hass).async_get(WIFI_SIGNAL).entity_category is EntityCategory.DIAGNOSTIC

    supervisor.client.network.interface_info.return_value = interface(
        "wlan0", InterfaceType.WIRELESS, "192.168.4.10/24", SSID, signal=40
    )
    await tick()
    assert hass.states.get(WIFI_SIGNAL).state == "40"
    # Not connected: no signal to show.
    lose_wifi(supervisor)
    await tick()
    assert hass.states.get(WIFI_SIGNAL).state == "unknown"
    # No answer from the Supervisor.
    supervisor.client.network.interface_info.side_effect = SupervisorError("busy")
    await tick()
    assert hass.states.get(WIFI_SIGNAL).state == "unavailable"


async def test_wifi_signal_without_password(hass: HomeAssistant, supervisor, entry) -> None:
    """Only the watchdog needs the password; the signal is found through the burner's address."""
    with patch(
        "custom_components.wildflame.async_find_wifi_link", return_value=WifiLink("wlan0", SSID)
    ) as find:
        await setup(hass, entry)
    find.assert_awaited_once_with(hass, entry.data[CONF_HOST])
    assert hass.states.get(WIFI_SIGNAL).state == "72"


async def test_no_wifi_signal_without_wifi_link(hass: HomeAssistant, supervisor, entry) -> None:
    # The fake burner is not on a Wi-Fi interface of the Supervisor.
    await setup(hass, entry)
    assert hass.states.get(WIFI_SIGNAL) is None
    supervisor.client.network.interface_info.assert_not_awaited()


async def test_setup_without_supervisor_answer(hass: HomeAssistant, supervisor, burner) -> None:
    supervisor.client.network.interface_info.side_effect = SupervisorError("busy")
    entry = wifi_entry(burner.host)
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(WIFI_SIGNAL).state == "unavailable"
