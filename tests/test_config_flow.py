"""Tests for setting up and reconfiguring the burner from the UI."""

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wildflame.api import WildflameConnectionError
from custom_components.wildflame.const import DOMAIN

from .fake_burner import FakeBurner

GET_STATUS = "custom_components.wildflame.config_flow.WildflameClient.get_status"


async def test_user_flow(hass: HomeAssistant, burner) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: f" {burner.host} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wild Flame"
    assert result["data"] == {CONF_HOST: burner.host}
    assert result["result"].unique_id == burner.host


async def test_user_flow_recovers_from_cannot_connect(hass: HomeAssistant, burner) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(GET_STATUS, side_effect=WildflameConnectionError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: burner.host}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: burner.host}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(hass: HomeAssistant, entry, burner) -> None:
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: burner.host}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(hass: HomeAssistant, entry, burner) -> None:
    entry.add_to_hass(hass)
    moved = FakeBurner()
    await moved.start()
    try:
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM

        with patch(GET_STATUS, side_effect=WildflameConnectionError):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_HOST: moved.host}
            )
        assert result["errors"] == {"base": "cannot_connect"}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: moved.host}
        )
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert entry.data == {CONF_HOST: moved.host}
        assert entry.unique_id == moved.host
        await hass.config_entries.async_unload(entry.entry_id)
    finally:
        await moved.stop()


async def test_reconfigure_same_host(hass: HomeAssistant, entry, burner) -> None:
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: burner.host}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == burner.host
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reconfigure_to_other_configured_burner(hass: HomeAssistant, entry, burner) -> None:
    entry.add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "10.0.0.2"}, unique_id="10.0.0.2")
    other.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.2"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == {CONF_HOST: burner.host}
