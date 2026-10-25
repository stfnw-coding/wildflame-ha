"""Restores Home Assistant's Wi-Fi connection to the burner when Home Assistant OS gives up on it.

When the burner's Wi-Fi drops briefly, NetworkManager can take the failed reconnect for a wrong password, ask
for a new one and, with nobody to answer, stop trying. Applying the Wi-Fi settings again through the Supervisor
(what Save does under Settings → System → Network) brings the connection back. That needs the Wi-Fi password:
the Supervisor never hands it out.
"""

from __future__ import annotations

import ipaddress
import logging
import math
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import override

from aiohasupervisor import SupervisorError
from aiohasupervisor.models import InterfaceType

from homeassistant.components.hassio import get_supervisor_client
from homeassistant.components.hassio.const import DATA_COMPONENT
from homeassistant.components.hassio.handler import HassioAPIError
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.hassio import is_hassio
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.hass_dict import HassKey

from .const import CONF_WIFI_INTERFACE, CONF_WIFI_SSID, DOMAIN, WIFI_CHECK_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

# The burner's access point turns Home Assistant away at times (association rejected, status 16) and lets it in
# a few seconds later, and NetworkManager gives up after a few tries in about 25 seconds. So a reconnect often
# fails and the next one, soon after, gets in: try every 2 minutes. Each try adds a connection profile in
# NetworkManager, so after 10 tries (a wrong password, say) only try every 30 minutes.
_RETRY_SECONDS = 2 * 60
_FAST_RETRIES = 10
_SLOW_RETRY_SECONDS = 30 * 60

# One watchdog per config entry. Not tied to the entry's setup: Home Assistant cancels an entry's tasks when
# its setup fails, and setup fails exactly while the burner is unreachable.
_WATCHDOGS: HassKey[dict[str, "WifiWatchdog"]] = HassKey(f"{DOMAIN}_wifi_watchdog")

# Supervisor waits up to 60 s for the connection to come up before it answers.
_UPDATE_TIMEOUT_SECONDS = 90


@dataclass(frozen=True, slots=True)
class WifiLink:
    """The Wi-Fi interface and network Home Assistant reaches the burner on."""

    interface: str
    ssid: str


async def async_find_wifi_link(hass: HomeAssistant, host: str) -> WifiLink | None:
    """Find the Wi-Fi interface whose network contains the burner's address.

    None if Home Assistant has no Supervisor, or reaches the burner some other way.
    """
    if not is_hassio(hass):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    try:
        info = await get_supervisor_client(hass).network.info()
    except SupervisorError:
        return None
    for interface in info.interfaces:
        if (
            interface.type is InterfaceType.WIRELESS
            and interface.wifi
            and interface.ipv4
            and any(address in ip.network for ip in interface.ipv4.address)
        ):
            return WifiLink(interface.interface, interface.wifi.ssid)
    return None


class WifiSignalCoordinator(DataUpdateCoordinator[int | None]):
    """Signal strength of Home Assistant's Wi-Fi connection to the burner, in % as NetworkManager reports it.

    None while the interface is not connected. Works without the Wi-Fi password: only the watchdog needs that.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, interface: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} Wi-Fi signal",
            update_interval=timedelta(seconds=WIFI_CHECK_INTERVAL_SECONDS),
            always_update=False,
        )
        self.interface = interface

    @override
    async def _async_update_data(self) -> int | None:
        try:
            info = await get_supervisor_client(self.hass).network.interface_info(self.interface)
        except SupervisorError as err:
            raise UpdateFailed(f"No Wi-Fi information from the Supervisor: {err}") from err
        if not (info.connected and info.wifi):
            return None
        return info.wifi.signal


@callback
def async_start_wifi_watchdog(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Watch the burner's Wi-Fi link if the entry has the Wi-Fi password; keeps a running watchdog."""
    watchdogs = hass.data.setdefault(_WATCHDOGS, {})
    current = watchdogs.get(entry.entry_id)
    if not (password := entry.data.get(CONF_PASSWORD)):
        async_stop_wifi_watchdog(hass, entry.entry_id)
        return
    link = WifiLink(entry.data[CONF_WIFI_INTERFACE], entry.data[CONF_WIFI_SSID])
    if current and current.link == link and current.password == password:
        return
    async_stop_wifi_watchdog(hass, entry.entry_id)
    watchdogs[entry.entry_id] = WifiWatchdog(hass, entry.entry_id, link, password)


@callback
def async_stop_wifi_watchdog(hass: HomeAssistant, entry_id: str) -> None:
    if watchdog := hass.data.get(_WATCHDOGS, {}).pop(entry_id, None):
        watchdog.async_stop()


class WifiWatchdog:
    """Reconnects the Wi-Fi interface to the burner's network when Home Assistant OS has given up on it.

    Checks every WIFI_CHECK_INTERVAL_SECONDS, whether or not the integration is set up: the burner does not
    need to answer for the Wi-Fi state to be known.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, link: WifiLink, password: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self.link = link
        self.password = password
        self._checking = False
        self._down_since: float | None = None
        self._next_reconnect = -math.inf
        self._reconnects = 0
        self._cancel: CALLBACK_TYPE | None = async_track_time_interval(
            hass,
            self._async_tick,
            timedelta(seconds=WIFI_CHECK_INTERVAL_SECONDS),
            name=f"{DOMAIN} Wi-Fi watchdog",
            cancel_on_shutdown=True,
        )

    @callback
    def async_stop(self) -> None:
        if self._cancel:
            self._cancel()
            self._cancel = None

    @callback
    def _async_tick(self, _now: object) -> None:
        entry = self._hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or entry.disabled_by:
            # Removed or disabled while not set up: Home Assistant then does not unload it.
            async_stop_wifi_watchdog(self._hass, self._entry_id)
            return
        if self._checking:
            return
        self._checking = True
        self._hass.async_create_background_task(self._async_check(entry), f"{DOMAIN} Wi-Fi check")

    async def _async_check(self, entry: ConfigEntry) -> None:
        try:
            await self._async_check_link(entry)
        except (SupervisorError, HassioAPIError) as err:
            _LOGGER.warning("Could not restore the Wi-Fi connection to the burner: %s", err or "no answer")
        finally:
            self._checking = False

    async def _async_check_link(self, entry: ConfigEntry) -> None:
        interface, ssid = self.link.interface, self.link.ssid
        network = get_supervisor_client(self._hass).network
        info = await network.interface_info(interface)
        if info.connected:
            # Connected or still connecting by itself. An address means it works: reconnect quickly next time.
            self._down_since = None
            if info.ipv4 and info.ipv4.address:
                self._next_reconnect, self._reconnects = -math.inf, 0
            return
        now = time.monotonic()
        if self._down_since is None:
            # Down since the last check at most; give NetworkManager until the next one to reconnect by itself.
            self._down_since = now
            return
        if now < self._next_reconnect:
            return
        if not any(ap.ssid == ssid for ap in await network.access_points(interface)):
            # Nothing to connect to: the burner is probably switched off at the mains.
            _LOGGER.debug("Wi-Fi network %s of the burner is not on the air", ssid)
            return
        _LOGGER.warning(
            "Home Assistant lost its Wi-Fi connection to the burner (%s on %s); reconnecting",
            ssid,
            interface,
        )
        self._reconnects += 1
        # Checks run every WIFI_CHECK_INTERVAL_SECONDS; the slack keeps a check that runs a little early in time.
        self._next_reconnect = now - WIFI_CHECK_INTERVAL_SECONDS / 2 + (
            _RETRY_SECONDS if self._reconnects < _FAST_RETRIES else _SLOW_RETRY_SECONDS
        )
        # Same settings as the README asks for. Sent as raw JSON: aiohasupervisor names the Wi-Fi
        # security field "method", but the Supervisor expects "auth".
        await self._hass.data[DATA_COMPONENT].send_command(
            f"/network/interface/{interface}/update",
            payload={
                "enabled": True,
                "ipv4": {"method": "auto"},
                "wifi": {
                    "mode": "infrastructure",
                    "auth": "wpa-psk",
                    "ssid": ssid,
                    "psk": self.password,
                },
            },
            timeout=_UPDATE_TIMEOUT_SECONDS,
        )
        if entry.state is ConfigEntryState.SETUP_RETRY:
            # Setup retries wait up to 10 minutes; the burner is reachable again now.
            self._hass.config_entries.async_schedule_reload(entry.entry_id)
