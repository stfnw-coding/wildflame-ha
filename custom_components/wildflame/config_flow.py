"""Config flow for the Wild Flame integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import DEFAULT_HOST, WildflameClient, WildflameError
from .const import DOMAIN

DEFAULT_NAME = "Haard"


class WildflameConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            client = WildflameClient(async_create_clientsession(self.hass), host)
            try:
                await client.get_status()
            except WildflameError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data={CONF_HOST: host}
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
