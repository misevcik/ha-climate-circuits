"""Hot water circulation pump: entities, hysteresis, control and Activity."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.climate_circuits.const import EVENT_ACTIVITY

from .conftest import HEAT_PUMP, HOUSE_OPTIONS

SENSOR = "sensor.circulation_return"
PUMP = "switch.circulation_pump"
STATE = "sensor.hot_water_circulation_state"
THRESHOLD = "number.hot_water_circulation_threshold"
DELTA = "number.hot_water_circulation_delta"
ENABLED = "switch.hot_water_circulation_enabled"
OPTIONS: dict[str, Any] = {
    **HOUSE_OPTIONS,
    "hot_water": {
        "circulation_sensor": SENSOR,
        "circulation_pump": PUMP,
        "threshold": 37.0,
        "delta": 1.0,
    },
}


@pytest.fixture
async def entry(hass: HomeAssistant, make_entry):
    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(SENSOR, "36.5")
    hass.states.async_set(PUMP, "off")
    entry = make_entry(options=OPTIONS)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _temperature(hass: HomeAssistant, value: str) -> None:
    hass.states.async_set(SENSOR, value)
    await hass.async_block_till_done()


async def test_entities_on_hot_water_device(hass: HomeAssistant, entry) -> None:
    assert hass.states.get(STATE).state == "stopped"
    assert float(hass.states.get(THRESHOLD).state) == 37.0
    assert float(hass.states.get(DELTA).state) == 1.0
    assert hass.states.get(ENABLED).state == "on"
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("climate_circuits", f"{entry.entry_id}_hot_water"), entry.entry_id
    )
    assert device is not None and device.name == "Hot water"


async def test_no_hot_water_without_config(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    entry = make_entry()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(STATE) is None
    assert hass.states.get(THRESHOLD) is None


async def test_circulation_temperature_sensor(hass: HomeAssistant, entry) -> None:
    temperature = "sensor.hot_water_circulation_temperature"
    assert float(hass.states.get(temperature).state) == 36.5
    await _temperature(hass, "35.2")
    assert float(hass.states.get(temperature).state) == 35.2
    entry.runtime_data.started -= 100  # past the start grace
    await _temperature(hass, "unavailable")
    assert hass.states.get(temperature).state == "unknown"


async def test_hysteresis_follows_the_real_pump(hass: HomeAssistant, entry) -> None:
    """In dry run somebody else drives the pump; the sensor shows what it would do beside it."""
    calls = async_mock_service(hass, "switch", "turn_on")
    await _temperature(hass, "35.9")
    assert hass.states.get(STATE).state == "running"
    hass.states.async_set(PUMP, "on")  # the pump follows (another automation)
    await _temperature(hass, "36.5")
    assert hass.states.get(STATE).state == "running"
    await _temperature(hass, "37.0")
    assert hass.states.get(STATE).state == "stopped"
    hass.states.async_set(PUMP, "off")
    await _temperature(hass, "36.5")
    assert hass.states.get(STATE).state == "stopped"
    attributes = hass.states.get(STATE).attributes
    assert attributes["starts_below"] == 36.0 and attributes["stops_at"] == 37.0
    assert attributes["controlled"] is False
    assert not calls  # dry run: the pump is never switched


async def test_pump_stopped_by_someone_else_is_not_running(hass: HomeAssistant, entry) -> None:
    await _temperature(hass, "35.9")
    hass.states.async_set(PUMP, "on")
    await _temperature(hass, "36.0")
    assert hass.states.get(STATE).state == "running"
    hass.states.async_set(PUMP, "off")  # the old automation stops it at 36.0
    await hass.async_block_till_done()
    assert hass.states.get(STATE).state == "stopped"


async def test_switches_pump_when_controlling(hass: HomeAssistant, entry) -> None:
    on = async_mock_service(hass, "switch", "turn_on")
    off = async_mock_service(hass, "switch", "turn_off")
    entry.runtime_data.set_control_equipment(True)
    await _temperature(hass, "35.0")
    assert [c.data["entity_id"] for c in on] == [PUMP]
    hass.states.async_set(PUMP, "on")
    await _temperature(hass, "37.5")
    assert [c.data["entity_id"] for c in off] == [PUMP]


async def test_disable_switch_stops_pump(hass: HomeAssistant, entry) -> None:
    await _temperature(hass, "30.0")
    await hass.services.async_call("switch", "turn_off", {"entity_id": ENABLED}, blocking=True)
    assert hass.states.get(STATE).state == "disabled"


async def test_unavailable_sensor(hass: HomeAssistant, entry) -> None:
    entry.runtime_data.started -= 100  # past the start grace
    await _temperature(hass, "unavailable")
    assert hass.states.get(STATE).state == "unavailable"


async def test_unavailable_sensor_is_tolerated_right_after_the_start(
    hass: HomeAssistant, entry
) -> None:
    events = []
    hass.bus.async_listen(EVENT_ACTIVITY, events.append)
    await _temperature(hass, "unavailable")
    assert hass.states.get(STATE).state != "unavailable"
    assert not events


async def test_threshold_change_without_reload(hass: HomeAssistant, entry) -> None:
    events = []
    hass.bus.async_listen(EVENT_ACTIVITY, events.append)
    with patch.object(hass.config_entries, "async_reload") as reload:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": THRESHOLD, "value": 40.0}, blocking=True
        )
        await hass.async_block_till_done()
    reload.assert_not_called()
    assert entry.options["hot_water"]["threshold"] == 40.0
    assert hass.states.get(STATE).attributes["stops_at"] == 40.0
    # 36.5 °C is now below 40 − 1: the pump starts.
    assert hass.states.get(STATE).state == "running"
    messages = [e.data["message"] for e in events]
    assert "Hot water circulation – threshold: 37 → 40" in messages
    assert any(m.startswith("On – circulation 36.5 °C is below 39.0 °C") for m in messages)


async def test_other_option_change_reloads(hass: HomeAssistant, entry) -> None:
    with patch.object(hass.config_entries, "async_reload") as reload:
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "hot_water": {**entry.options["hot_water"], "circulation_pump": "switch.other"},
            },
        )
        await hass.async_block_till_done()
    reload.assert_called_once()


async def test_schema_card_gets_the_hot_water_entities(hass: HomeAssistant, entry) -> None:
    hw = hass.states.get("sensor.climate_circuits_mode").attributes["layout"]["hot_water"]
    assert hw["state"] == STATE
    assert hw["threshold"] == THRESHOLD and hw["delta"] == DELTA and hw["enabled"] == ENABLED
    assert hw["temperature"] == "sensor.hot_water_circulation_temperature"
    assert hw["tank"] is None
