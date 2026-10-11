"""Thermostats are switched with the house mode, the other set first and confirmed off."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.climate_circuits.const import EVENT_ACTIVITY

from .conftest import HEAT_PUMP, HOUSE_OPTIONS, circuit_data

HEAT = ["climate.kitchen", "climate.office"]
COOL = ["climate.kitchen_cool", "climate.office_cool"]
F1 = circuit_data("F1", zones={"heating_zones": HEAT, "cooling_zones": COOL})
OPTIONS: dict[str, Any] = {
    **HOUSE_OPTIONS,
    "zone_control": {"switch_zones": True},
}


class Calls(list):
    """Recorded service calls; thermostats in stuck ignore commands."""

    stuck: set[str]


@pytest.fixture
def calls(hass: HomeAssistant) -> Calls:
    """Record climate.set_hvac_mode and apply it like a thermostat would (unless told not to)."""
    recorded = Calls()
    recorded.stuck = stuck = set()

    async def set_hvac_mode(call: ServiceCall) -> None:
        recorded.append(call)
        entity_id = call.data["entity_id"]
        if entity_id not in stuck:
            hass.states.async_set(entity_id, call.data["hvac_mode"])

    async def switch(call: ServiceCall) -> None:
        recorded.append(call)
        hass.states.async_set(call.data["entity_id"], "on" if call.service == "turn_on" else "off")

    hass.services.async_register("climate", "set_hvac_mode", set_hvac_mode)
    hass.services.async_register("input_boolean", "turn_on", switch)
    hass.services.async_register("input_boolean", "turn_off", switch)
    return recorded


@pytest.fixture
async def entry(hass: HomeAssistant, make_entry, calls):
    hass.states.async_set(HEAT_PUMP, "heat")
    for zone in HEAT:
        hass.states.async_set(zone, "heat")
    for zone in COOL:
        hass.states.async_set(zone, "off")
    entry = make_entry(F1, options=OPTIONS)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _modes(hass: HomeAssistant, zones: list[str]) -> list[str]:
    return [hass.states.get(z).state for z in zones]


async def _control(hass: HomeAssistant, entry) -> None:
    entry.runtime_data.set_control_equipment(True)
    await hass.async_block_till_done()


async def test_heat_to_cool_turns_heating_off_before_cooling_on(
    hass: HomeAssistant, entry, calls
) -> None:
    await _control(hass, entry)
    calls.clear()
    hass.states.async_set(HEAT_PUMP, "cool")
    await hass.async_block_till_done()
    assert _modes(hass, HEAT) == ["off", "off"]
    assert _modes(hass, COOL) == ["cool", "cool"]
    zone_calls = [
        (c.data["entity_id"], c.data["hvac_mode"]) for c in calls if c.domain == "climate"
    ]
    first_on = next(i for i, (_, m) in enumerate(zone_calls) if m == "cool")
    assert {z for z, m in zone_calls[:first_on]} == set(HEAT)  # all heating off first


async def test_cooling_waits_while_a_heating_thermostat_stays_on(
    hass: HomeAssistant, entry, calls
) -> None:
    await _control(hass, entry)
    calls.stuck.add("climate.kitchen")
    hass.states.async_set(HEAT_PUMP, "cool")
    await hass.async_block_till_done()
    assert _modes(hass, COOL) == ["off", "off"]
    attributes = hass.states.get("sensor.climate_circuits_mode").attributes
    assert attributes["zones_still_on"] == ["kitchen"]
    # The thermostat finally turns off: cooling starts.
    calls.stuck.clear()
    hass.states.async_set("climate.kitchen", "off")
    await hass.async_block_till_done()
    assert _modes(hass, COOL) == ["cool", "cool"]


async def test_stray_heating_thermostat_is_turned_off_in_cooling(
    hass: HomeAssistant, entry, calls
) -> None:
    events = []
    hass.bus.async_listen(EVENT_ACTIVITY, events.append)
    await _control(hass, entry)
    hass.states.async_set(HEAT_PUMP, "cool")
    await hass.async_block_till_done()
    hass.states.async_set("climate.office", "heat")  # a schedule or a person
    await hass.async_block_till_done()
    assert hass.states.get("climate.office").state == "off"
    assert any("office – on in cooling mode, turning off" in e.data["message"] for e in events)


async def test_dry_run_only_tells(hass: HomeAssistant, entry, calls) -> None:
    events = []
    hass.bus.async_listen(EVENT_ACTIVITY, events.append)
    hass.states.async_set(HEAT_PUMP, "cool")
    await hass.async_block_till_done()
    assert not [c for c in calls if c.domain == "climate"]
    assert _modes(hass, HEAT) == ["heat", "heat"]
    messages = [e.data["message"] for e in events]
    assert (
        "Switching to cooling: turning off 2 (kitchen, office), then turning on "
        "2 (kitchen cool, office cool) (dry run, thermostats not switched)"
    ) in messages


async def test_failed_turn_off_is_reported(hass: HomeAssistant, entry, calls) -> None:
    events = []
    hass.bus.async_listen(EVENT_ACTIVITY, events.append)
    await _control(hass, entry)
    calls.stuck.add("climate.kitchen")
    switcher = entry.runtime_data.zones
    hass.states.async_set(HEAT_PUMP, "cool")
    await hass.async_block_till_done()
    for _ in range(4):
        # Pretend the retry interval passed.
        switcher._sent = {z: (m, t - 1000, n) for z, (m, t, n) in switcher._sent.items()}
        entry.runtime_data.evaluate()
        await hass.async_block_till_done()
    assert any("Could not turn off kitchen after 3 attempts" in e.data["message"] for e in events)
    assert _modes(hass, COOL) == ["off", "off"]  # cooling never starts while it is on


async def test_disabled_does_nothing(hass: HomeAssistant, make_entry, calls) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    for zone in HEAT:
        hass.states.async_set(zone, "heat")
    options = {**OPTIONS, "zone_control": {"switch_zones": False}}
    entry = make_entry(F1, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _control(hass, entry)
    hass.states.async_set(HEAT_PUMP, "cool")
    await hass.async_block_till_done()
    assert _modes(hass, HEAT) == ["heat", "heat"]
