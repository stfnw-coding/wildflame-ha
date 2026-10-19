"""Config flow for the Wild Flame integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, override

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DEFAULT_HOST, WildflameClient, WildflameError
from .const import DOMAIN, MANUFACTURER

if TYPE_CHECKING:
    import probatio

# HA 2026.9 types flow schemas as probatio.Schema; voluptuous is API-compatible
# and keeps older HA versions working.
SCHEMA = cast(
    "probatio.Schema", vol.Schema({vol.Required(CONF_HOST, default=DEFAULT_HOST): str})
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
            if not (errors := await self._async_test_connection(host)):
                return self.async_create_entry(title=MANUFACTURER, data={CONF_HOST: host})

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
            if not (errors := await self._async_test_connection(host)):
                return self.async_update_reload_and_abort(
                    entry, unique_id=host, data_updates={CONF_HOST: host}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input or entry.data),
            errors=errors,
        )

    async def _async_test_connection(self, host: str) -> dict[str, str]:
        client = WildflameClient(async_get_clientsession(self.hass), host)
        try:
            await client.get_status()
        except WildflameError:
            return {"base": "cannot_connect"}
        return {}
