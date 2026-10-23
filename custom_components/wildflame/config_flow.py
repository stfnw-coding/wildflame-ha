"""Config flow for the Wild Flame integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, override

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import DEFAULT_HOST, WildflameClient, WildflameError
from .const import CONF_WIFI_INTERFACE, CONF_WIFI_SSID, DOMAIN, MANUFACTURER
from .wifi import async_find_wifi_link

if TYPE_CHECKING:
    import probatio

# HA 2026.9 types flow schemas as probatio.Schema; voluptuous is API-compatible
# and keeps older HA versions working.
SCHEMA = cast(
    "probatio.Schema",
    vol.Schema(
        {
            vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
            # The burner's Wi-Fi password, only for reconnecting Home Assistant OS to the burner's Wi-Fi.
            vol.Optional(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    ),
)


class WildflameConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            data, errors = await self._async_validate(host, user_input.get(CONF_PASSWORD))
            if not errors:
                return self.async_create_entry(title=MANUFACTURER, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            # The host is the unique id: the burner exposes no serial number or MAC address.
            if host != entry.unique_id:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
            data, errors = await self._async_validate(host, user_input.get(CONF_PASSWORD))
            if not errors:
                return self.async_update_reload_and_abort(entry, unique_id=host, data=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input or entry.data),
            errors=errors,
        )

    async def _async_validate(
        self, host: str, password: str | None
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Check the burner answers and, with a password, find the Wi-Fi interface it is on."""
        client = WildflameClient(async_get_clientsession(self.hass), host)
        try:
            await client.get_status()
        except WildflameError:
            return {}, {"base": "cannot_connect"}
        if not password:
            return {CONF_HOST: host}, {}
        if not (link := await async_find_wifi_link(self.hass, host)):
            return {}, {CONF_PASSWORD: "wifi_not_found"}
        return {
            CONF_HOST: host,
            CONF_PASSWORD: password,
            CONF_WIFI_INTERFACE: link.interface,
            CONF_WIFI_SSID: link.ssid,
        }, {}
