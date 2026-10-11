"""What a circuit shows: calling thermostats and the mixing valve position."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .conftest import HEAT_PUMP, OUTDOOR, circuit_data, set_thermostat

COVER = "cover.mixer_f1"
SUPPLY = "sensor.f1_supply"
F1 = circuit_data(
    "F1",
    zones={"heating_zones": ["climate.office", "climate.kitchen"]},
    outputs={"mixer_position": COVER, "supply_sensor": SUPPLY},
)
CALLING = "sensor.f1_calling_zones"
MIXER = "sensor.f1_mixer_position"


async def _setup(hass: HomeAssistant, make_entry, *circuits) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(OUTDOOR, "0")
    hass.states.async_set(COVER, "open", {"current_position": 61})
    hass.states.async_set(SUPPLY, "33.2")
    set_thermostat(hass, "climate.office", "idle")
    set_thermostat(hass, "climate.kitchen", "idle")
    entry = make_entry(*circuits)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_calling_zones_lists_thermostat_names(hass: HomeAssistant, make_entry) -> None:
    await _setup(hass, make_entry, F1)
    assert hass.states.get(CALLING).state == "–"
    set_thermostat(hass, "climate.office", "heating")
    set_thermostat(hass, "climate.kitchen", "heating")
    await hass.async_block_till_done()
    state = hass.states.get(CALLING)
    assert state.state == "office, kitchen"
    assert state.attributes["count"] == 2
    assert state.attributes["zones"] == ["climate.office", "climate.kitchen"]


async def test_mixer_position_from_cover(hass: HomeAssistant, make_entry) -> None:
    await _setup(hass, make_entry, F1)
    state = hass.states.get(MIXER)
    assert float(state.state) == 61
    assert state.attributes["supply_temperature"] == 33.2
    assert state.attributes["source"] == COVER
    hass.states.async_set(COVER, "closed", {"current_position": 0})
    await hass.async_block_till_done()
    assert float(hass.states.get(MIXER).state) == 0


async def test_no_mixer_sensor_without_cover(hass: HomeAssistant, make_entry) -> None:
    await _setup(hass, make_entry, circuit_data("F1"))
    assert hass.states.get(MIXER) is None
    assert hass.states.get(CALLING) is not None
