"""Activity (logbook) entries explaining decisions."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.climate_circuits.const import EVENT_ACTIVITY

from .conftest import HEAT_PUMP, circuit_data, set_thermostat

F1 = circuit_data("F1", zones={"heating_zones": ["climate.office"]})


async def _setup(hass: HomeAssistant, make_entry):
    entry = make_entry(F1)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_start_logs_mode_and_circuit_once(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat", {"friendly_name": "Heat pump"})
    set_thermostat(hass, "climate.office", "idle")
    events = async_capture_events(hass, EVENT_ACTIVITY)
    await _setup(hass, make_entry)

    messages = [e.data["message"] for e in events]
    assert messages == [
        "House mode: heating – decided by: Heat pump (source entity heat)",
        "Not heating – no zone asks for heat: 1 reached target",
    ]
    assert events[0].data["entity_id"] == "sensor.climate_circuits_mode"
    assert events[1].data["entity_id"] == "sensor.f1_state"

    # Nothing new to say: no new entries.
    hass.states.async_set("sensor.outdoor", "5")
    await hass.async_block_till_done()
    assert len(events) == 2


async def test_mode_never_starts_off(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    seen: list[str] = []
    hass.bus.async_listen(
        "state_changed",
        lambda e: (
            seen.append(e.data["new_state"].state)
            if e.data["entity_id"] == "sensor.climate_circuits_mode" and e.data["new_state"]
            else None
        ),
    )
    await _setup(hass, make_entry)
    assert seen and set(seen) == {"heat"}


async def test_zone_starting_to_heat_is_logged(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    set_thermostat(hass, "climate.office", "idle")
    await _setup(hass, make_entry)
    events = async_capture_events(hass, EVENT_ACTIVITY)

    set_thermostat(hass, "climate.office", "heating")
    await hass.async_block_till_done()
    assert [e.data["message"] for e in events] == ["Heating – 1 of 1 zones: office"]


async def test_curve_change_is_logged(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    await _setup(hass, make_entry)
    events = async_capture_events(hass, EVENT_ACTIVITY)
    await hass.services.async_call(
        "climate_circuits",
        "set_curve",
        {"entity_id": "sensor.f1_target_water_temperature", "mode": "cool", "slope": 0.8},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert events[0].data["message"] == "Cooling curve – slope: 0.5 → 0.8"
    assert events[0].data["entity_id"] == "sensor.f1_target_water_temperature"
