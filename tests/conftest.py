"""Fixtures for Wild Flame tests."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wildflame.const import DOMAIN

from .fake_burner import FakeBurner


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def burner(socket_enabled):
    fake = FakeBurner()
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
def entry(burner) -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, title="Haard", data={"host": burner.host}, unique_id=burner.host)
