"""Tests for the burner client and status parser."""

import aiohttp
import pytest

from custom_components.wildflame.api import (
    BurnerState,
    WildflameClient,
    WildflameConnectionError,
    WildflameResponseError,
    WildflameStatus,
)


def test_parse_captured_status() -> None:
    status = WildflameStatus.parse(" usart1=2, usart2=0, usart3=1, usart4=45, usart5=20, usart6=0, usart7=1")
    assert status.fuel_percent == 20
    assert status.flame_level == 1
    assert status.humidity == 45
    assert status.temperature == 20
    assert not status.child_lock
    assert status.state is BurnerState.BURNING


@pytest.mark.parametrize(
    ("body", "state"),
    [
        # Sequence captured on 2026-10-18.
        (" usart1=2, usart2=6, usart3=0, usart4=45, usart5=20, usart6=0, usart7=0", BurnerState.OFF),
        (" usart1=2, usart2=10, usart3=0, usart4=45, usart5=20, usart6=0, usart7=1", BurnerState.WARMING_UP),
        (" usart1=2, usart2=0, usart3=5, usart4=45, usart5=20, usart6=0, usart7=1", BurnerState.BURNING),
        (" usart1=2, usart2=1, usart3=0, usart4=45, usart5=20, usart6=0, usart7=0", BurnerState.COOLING),
        # Phase codes not seen yet (errors?) must not be mistaken for a normal state.
        (" usart1=2, usart2=7, usart3=0, usart4=45, usart5=20, usart6=0, usart7=0", BurnerState.UNKNOWN_PHASE),
        (" usart1=2, usart2=7, usart3=5, usart4=45, usart5=20, usart6=0, usart7=1", BurnerState.UNKNOWN_PHASE),
    ],
)
def test_derived_state(body: str, state: BurnerState) -> None:
    assert WildflameStatus.parse(body).state is state


def test_parse_incomplete() -> None:
    with pytest.raises(WildflameResponseError):
        WildflameStatus.parse(" usart1=2, usart2=0")


async def test_client_against_fake(burner) -> None:
    async with aiohttp.ClientSession() as session:
        client = WildflameClient(session, burner.host)
        assert (await client.get_status()).state is BurnerState.OFF
        await client.send_command("82534KL")
        assert burner.commands == ["82534KL"]
        assert (await client.get_status()).state is BurnerState.WARMING_UP


async def test_client_unreachable(socket_enabled) -> None:
    async with aiohttp.ClientSession() as session:
        client = WildflameClient(session, "127.0.0.1:9", timeout=1)
        with pytest.raises(WildflameConnectionError):
            await client.get_status()
