"""Curve editing with the set_curve service and the curve picture."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import HEAT_PUMP, OUTDOOR, circuit_data, set_thermostat

F1 = circuit_data("F1", zones={"heating_zones": ["climate.office"]})
TARGET = "sensor.f1_target_water_temperature"


@pytest.fixture
async def entry(hass: HomeAssistant, make_entry):
    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(OUTDOOR, "0")
    set_thermostat(hass, "climate.office", "heating")
    entry = make_entry(F1)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _set_curve(hass: HomeAssistant, mode: str, **values: Any) -> None:
    await hass.services.async_call(
        "climate_circuits",
        "set_curve",
        {"entity_id": TARGET, "mode": mode, **values},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_no_curve_number_entities(hass: HomeAssistant, entry) -> None:
    registry = er.async_get(hass)
    numbers = [e.translation_key for e in registry.entities.values() if e.domain == "number"]
    assert numbers and not [key for key in numbers if "curve" in (key or "")]


async def test_set_curve_updates_target_without_reload(hass: HomeAssistant, entry) -> None:
    # At 0 °C outside: 40.8 °C with the 50 °C design point, 44.1 °C with 55 °C.
    assert float(hass.states.get(TARGET).state) == 40.8
    with patch.object(hass.config_entries, "async_reload") as reload:
        await _set_curve(hass, "heat", maximum=60.0, design_supply=55.0)
    reload.assert_not_called()
    assert float(hass.states.get(TARGET).state) == 44.1
    assert hass.states.get(TARGET).attributes["heat_curve"]["design_supply"] == 55.0
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data["heat_curve"]["design_supply"] == 55.0
    assert subentry.data["heat_curve"]["minimum"] == 35.0


async def test_invalid_curves_are_rejected(hass: HomeAssistant, entry) -> None:
    with pytest.raises(ServiceValidationError):
        await _set_curve(hass, "heat", minimum=60.0)
    with pytest.raises(ServiceValidationError):
        await _set_curve(hass, "heat", design_outdoor=25.0)
    with pytest.raises(ServiceValidationError):
        await _set_curve(hass, "cool", design_supply=40.0)
    assert hass.states.get(TARGET).attributes["heat_curve"]["minimum"] == 35.0


async def test_other_changes_still_reload(hass: HomeAssistant, entry) -> None:
    subentry = next(iter(entry.subentries.values()))
    with patch.object(hass.config_entries, "async_reload") as reload:
        hass.config_entries.async_update_subentry(
            entry, subentry, data={**subentry.data, "zones": {"heating_zones": []}}
        )
        await hass.async_block_till_done()
    reload.assert_called_once()


async def test_card_data_on_target_sensor(hass: HomeAssistant, entry) -> None:
    attributes = hass.states.get(TARGET).attributes
    assert attributes["house_mode"] == "heat"
    assert attributes["heat_curve"] == {
        "room": 22.0,
        "design_outdoor": -15.0,
        "design_supply": 50.0,
        "exponent": 1.3,
        "minimum": 35.0,
        "maximum": 50.0,
        "correction": 0.0,
    }
    assert attributes["cool_curve"]["slope"] == 0.5
    assert "curve" not in attributes
