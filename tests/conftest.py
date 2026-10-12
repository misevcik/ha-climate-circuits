"""Fixtures for Climate Circuits tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_circuits.const import (
    DOMAIN,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_SOURCE,
)

HEAT_PUMP = "climate.heat_pump"
TANK = "sensor.tank"
OUTDOOR = "sensor.outdoor"

HOUSE_OPTIONS: dict[str, Any] = {
    "mode": {"capabilities": ["heat", "cool"], "mode_entity": HEAT_PUMP},
    "fallback": {"kind": "tank", "sensor": TANK, "heat_threshold": 28.0, "cool_threshold": 22.0},
    "weather": {"outdoor_sensor": OUTDOOR},
    "display": {"info_sensors": ["sensor.hot_water"]},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the custom integration in every test."""


def set_thermostat(
    hass: HomeAssistant, entity_id: str, action: str, temperature: float = 22.0
) -> None:
    """Create or update a thermostat with an hvac_action."""
    hass.states.async_set(
        entity_id, "heat", {"hvac_action": action, "current_temperature": temperature}
    )


def circuit_data(name: str, **sections: dict[str, Any]) -> ConfigSubentryData:
    """Build subentry data for a circuit."""
    data: dict[str, Any] = {
        "name": name,
        "zones": {},
        "heat_curve": {},
        "cool_curve": {},
        "outputs": {},
    }
    data.update(sections)
    return ConfigSubentryData(
        subentry_type=SUBENTRY_TYPE_CIRCUIT, title=name, unique_id=None, data=data
    )


def source_data(name: str, sensor: str | None = None) -> ConfigSubentryData:
    """Build subentry data for a heat source."""
    data = {"name": name, **({"temperature_sensor": sensor} if sensor else {})}
    return ConfigSubentryData(
        subentry_type=SUBENTRY_TYPE_SOURCE, title=name, unique_id=None, data=data
    )


@pytest.fixture
def make_entry(hass: HomeAssistant) -> Callable[..., MockConfigEntry]:
    """Factory for a house entry with circuits."""

    def _make(*circuits: ConfigSubentryData, options: dict[str, Any] | None = None):
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Climate Circuits",
            options=options if options is not None else HOUSE_OPTIONS,
            subentries_data=circuits,
        )
        entry.add_to_hass(hass)
        return entry

    return _make
