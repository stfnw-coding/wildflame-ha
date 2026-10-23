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

from aiohasupervisor import SupervisorError
from aiohasupervisor.models import InterfaceType

from homeassistant.components.hassio import get_supervisor_client
from homeassistant.components.hassio.const import DATA_COMPONENT
from homeassistant.components.hassio.handler import HassioAPIError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.hassio import is_hassio
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN, WIFI_CHECK_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

# A reconnect can add a connection profile in NetworkManager, so if one does not help (a wrong password, say),
# wait 4, 8, 16, 32 and then 64 minutes before trying again.
_MAX_BACKOFF_DOUBLINGS = 5


@dataclass(slots=True)
class _RecoveryState:
    next_check: float = -math.inf
    reconnects: int = 0


# Per config entry. Kept outside the coordinator: setup retries create a new coordinator each time.
_STATE: HassKey[dict[str, _RecoveryState]] = HassKey(f"{DOMAIN}_wifi_recovery")

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


class WifiRecovery:
    """Reconnects the Wi-Fi interface to the burner's network when it has given up."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, link: WifiLink, password: str
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._link = link
        self._password = password
        self._state = hass.data.setdefault(_STATE, {}).setdefault(entry.entry_id, _RecoveryState())

    @callback
    def async_burner_reachable(self) -> None:
        self._state.reconnects = 0

    @callback
    def async_burner_unreachable(self) -> None:
        """Check the Wi-Fi connection in the background, at most every WIFI_CHECK_INTERVAL_SECONDS."""
        now = time.monotonic()
        if now < self._state.next_check:
            return
        self._state.next_check = now + WIFI_CHECK_INTERVAL_SECONDS
        self._entry.async_create_background_task(
            self._hass, self._async_check(), f"{DOMAIN} Wi-Fi recovery"
        )

    async def _async_check(self) -> None:
        interface, ssid = self._link.interface, self._link.ssid
        network = get_supervisor_client(self._hass).network
        try:
            if (await network.interface_info(interface)).connected:
                return  # The Wi-Fi connection is fine; the burner itself does not answer.
            if not any(ap.ssid == ssid for ap in await network.access_points(interface)):
                # Nothing to connect to: the burner is probably switched off at the mains.
                _LOGGER.debug("Wi-Fi network %s of the burner is not on the air", ssid)
                return
            _LOGGER.warning(
                "Home Assistant lost its Wi-Fi connection to the burner (%s on %s); reconnecting",
                ssid,
                interface,
            )
            self._state.reconnects += 1
            self._state.next_check = time.monotonic() + WIFI_CHECK_INTERVAL_SECONDS * 2 ** min(
                self._state.reconnects, _MAX_BACKOFF_DOUBLINGS
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
                        "psk": self._password,
                    },
                },
                timeout=_UPDATE_TIMEOUT_SECONDS,
            )
        except (SupervisorError, HassioAPIError) as err:
            _LOGGER.warning("Could not restore the Wi-Fi connection to the burner: %s", err or "no answer")
