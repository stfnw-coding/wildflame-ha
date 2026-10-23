"""Tests for reconnecting Home Assistant OS to the burner's Wi-Fi."""

from ipaddress import ip_interface
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohasupervisor import SupervisorError
from aiohasupervisor.models import InterfaceType
from homeassistant.components.hassio.const import DATA_COMPONENT
from homeassistant.components.hassio.handler import HassioAPIError
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.wildflame.const import CONF_WIFI_INTERFACE, CONF_WIFI_SSID, DOMAIN
from custom_components.wildflame.wifi import WifiLink, WifiRecovery, async_find_wifi_link

from .test_integration import setup

SSID = "WILDFLAME800"
PASSWORD = "burner-secret"


def interface(name, kind, address, ssid=None, connected=True):
    return SimpleNamespace(
        interface=name,
        type=kind,
        connected=connected,
        ipv4=SimpleNamespace(address=[ip_interface(address)]) if address else None,
        wifi=SimpleNamespace(ssid=ssid) if ssid else None,
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


async def test_reconnects_when_wifi_gave_up(hass: HomeAssistant, supervisor) -> None:
    entry = wifi_entry("192.168.4.1")
    entry.add_to_hass(hass)
    lose_wifi(supervisor)
    WifiRecovery(hass, entry, WifiLink("wlan0", SSID), PASSWORD).async_burner_unreachable()
    await hass.async_block_till_done()
    supervisor.send_command.assert_awaited_once()
    command, kwargs = supervisor.send_command.await_args.args[0], supervisor.send_command.await_args.kwargs
    assert command == "/network/interface/wlan0/update"
    assert kwargs["payload"] == {
        "enabled": True,
        "ipv4": {"method": "auto"},
        "wifi": {"mode": "infrastructure", "auth": "wpa-psk", "ssid": SSID, "psk": PASSWORD},
    }


async def test_leaves_working_wifi_alone(hass: HomeAssistant, supervisor) -> None:
    entry = wifi_entry("192.168.4.1")
    entry.add_to_hass(hass)
    WifiRecovery(hass, entry, WifiLink("wlan0", SSID), PASSWORD).async_burner_unreachable()
    await hass.async_block_till_done()
    supervisor.client.network.access_points.assert_not_awaited()
    supervisor.send_command.assert_not_awaited()


async def test_waits_for_burner_wifi_on_the_air(hass: HomeAssistant, supervisor) -> None:
    entry = wifi_entry("192.168.4.1")
    entry.add_to_hass(hass)
    lose_wifi(supervisor)
    supervisor.client.network.access_points.return_value = [SimpleNamespace(ssid="Neighbours")]
    WifiRecovery(hass, entry, WifiLink("wlan0", SSID), PASSWORD).async_burner_unreachable()
    await hass.async_block_till_done()
    supervisor.send_command.assert_not_awaited()


async def unreachable_at(hass: HomeAssistant, recovery: WifiRecovery, now: float) -> None:
    with patch("custom_components.wildflame.wifi.time.monotonic", return_value=now):
        recovery.async_burner_unreachable()
        await hass.async_block_till_done()


async def test_checks_at_most_every_interval(hass: HomeAssistant, supervisor) -> None:
    entry = wifi_entry("192.168.4.1")
    entry.add_to_hass(hass)
    link = WifiLink("wlan0", SSID)
    await unreachable_at(hass, WifiRecovery(hass, entry, link, PASSWORD), 1000)
    # A setup retry makes a new instance; it must not check again right away.
    await unreachable_at(hass, WifiRecovery(hass, entry, link, PASSWORD), 1119)
    assert supervisor.client.network.interface_info.await_count == 1
    await unreachable_at(hass, WifiRecovery(hass, entry, link, PASSWORD), 1120)
    assert supervisor.client.network.interface_info.await_count == 2


async def test_reconnects_back_off_until_burner_answers(hass: HomeAssistant, supervisor) -> None:
    entry = wifi_entry("192.168.4.1")
    entry.add_to_hass(hass)
    lose_wifi(supervisor)
    recovery = WifiRecovery(hass, entry, WifiLink("wlan0", SSID), PASSWORD)
    await unreachable_at(hass, recovery, 1000)
    assert supervisor.send_command.await_count == 1
    # The reconnect did not help: wait 4 minutes, then 8.
    await unreachable_at(hass, recovery, 1000 + 239)
    assert supervisor.send_command.await_count == 1
    await unreachable_at(hass, recovery, 1000 + 240)
    assert supervisor.send_command.await_count == 2
    await unreachable_at(hass, recovery, 1240 + 479)
    assert supervisor.send_command.await_count == 2
    await unreachable_at(hass, recovery, 1240 + 480)
    assert supervisor.send_command.await_count == 3

    # Once the burner answered, a next loss is handled with a short wait again.
    recovery.async_burner_reachable()
    await unreachable_at(hass, recovery, 1720 + 960)
    await unreachable_at(hass, recovery, 2680 + 240)
    assert supervisor.send_command.await_count == 5


@pytest.mark.parametrize("error", [SupervisorError("busy"), HassioAPIError()])
async def test_reconnect_failure_is_logged(
    hass: HomeAssistant, supervisor, caplog: pytest.LogCaptureFixture, error
) -> None:
    entry = wifi_entry("192.168.4.1")
    entry.add_to_hass(hass)
    lose_wifi(supervisor)
    supervisor.send_command.side_effect = error
    WifiRecovery(hass, entry, WifiLink("wlan0", SSID), PASSWORD).async_burner_unreachable()
    await hass.async_block_till_done()
    assert "Could not restore the Wi-Fi connection to the burner" in caplog.text


async def test_unreachable_burner_triggers_recovery(hass: HomeAssistant, supervisor, burner) -> None:
    entry = wifi_entry(burner.host)
    await setup(hass, entry)
    supervisor.client.network.interface_info.assert_not_awaited()

    await burner.stop()
    lose_wifi(supervisor)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    supervisor.send_command.assert_awaited_once()


async def test_no_recovery_without_password(hass: HomeAssistant, supervisor, entry, burner) -> None:
    await setup(hass, entry)
    await burner.stop()
    lose_wifi(supervisor)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    supervisor.client.network.interface_info.assert_not_awaited()
    supervisor.send_command.assert_not_awaited()


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


async def test_reconfigure_removes_password(hass: HomeAssistant, supervisor, burner) -> None:
    entry = wifi_entry(burner.host)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: burner.host})
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_HOST: burner.host}
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
