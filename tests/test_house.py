"""House runtime: mode, demand and target water temperature as entities."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.climate_circuits.const import DOMAIN

from .conftest import HEAT_PUMP, OUTDOOR, TANK, circuit_data, set_thermostat

MODE = "sensor.climate_circuits_mode"
STATUS = "sensor.climate_circuits_status"
OVERRIDE = "select.climate_circuits_mode_override"
CONTROL = "switch.climate_circuits_control_equipment"
F1_DEMAND = "binary_sensor.f1_demand"
F1_TARGET = "sensor.f1_target_water_temperature"
GF_DEMAND = "binary_sensor.gf_demand"

F1 = circuit_data(
    "F1",
    zones={
        "heating_zones": ["climate.office", "climate.kitchen"],
        "cooling_zones": ["climate.office_ac"],
        "humidity_sensors": ["sensor.office_humidity"],
    },
)
GF = circuit_data("GF")


async def _setup(hass: HomeAssistant, make_entry, *circuits) -> None:
    entry = make_entry(*circuits)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_mode_follows_heat_pump(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    await _setup(hass, make_entry, F1)
    state = hass.states.get(MODE)
    assert state.state == "heat"
    assert state.attributes["source"] == "entity"

    hass.states.async_set(HEAT_PUMP, "cool")
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "cool"


async def test_tank_fallback_when_heat_pump_unavailable(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "unavailable")
    hass.states.async_set(TANK, "35")
    await _setup(hass, make_entry, F1)
    state = hass.states.get(MODE)
    assert state.state == "heat"
    assert state.attributes["source"] == "fallback"

    # Between thresholds the last mode is kept.
    hass.states.async_set(TANK, "25")
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "heat"


async def test_override(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    await _setup(hass, make_entry, F1)
    assert hass.states.get(OVERRIDE).attributes["options"] == ["auto", "heat", "cool", "off"]

    await hass.services.async_call(
        "select", "select_option", {"entity_id": OVERRIDE, "option": "off"}, blocking=True
    )
    state = hass.states.get(MODE)
    assert state.state == "off"
    assert state.attributes["source"] == "override"


async def test_demand_and_target(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(OUTDOOR, "14.9")
    set_thermostat(hass, "climate.office", "idle")
    set_thermostat(hass, "climate.kitchen", "idle")
    await _setup(hass, make_entry, F1, GF)

    assert hass.states.get(F1_DEMAND).state == "off"
    # Ground floor has no zones and runs with the mode.
    assert hass.states.get(GF_DEMAND).state == "on"
    # 22 + 28 · (7.1/37)^(1/1.3) = 29.9 → clamped to the 35 °C minimum.
    target = hass.states.get(F1_TARGET)
    assert float(target.state) == 35.0
    assert target.attributes["reason"] == "curve clamped to minimum"

    set_thermostat(hass, "climate.kitchen", "heating")
    await hass.async_block_till_done()
    demand = hass.states.get(F1_DEMAND)
    assert demand.state == "on"
    assert demand.attributes["zones"] == ["climate.kitchen"]

    hass.states.async_set(OUTDOOR, "-5")
    await hass.async_block_till_done()
    # 22 + 28 · (27/37)^(1/1.3) = 44.0
    assert float(hass.states.get(F1_TARGET).state) == 44.0


async def test_cooling_target_respects_dew_point(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "cool")
    hass.states.async_set(OUTDOOR, "40")
    hass.states.async_set("sensor.office_humidity", "70")
    set_thermostat(hass, "climate.office_ac", "cooling", temperature=27.0)
    await _setup(hass, make_entry, F1)

    target = hass.states.get(F1_TARGET)
    # Dew point of 27 °C / 70 % is about 21.1 °C; + 2 K is above the 16 °C curve value.
    assert float(target.state) == 23.1
    assert target.attributes["reason"].startswith("dew point")
    assert hass.states.get(F1_DEMAND).state == "on"


async def test_control_switch_and_status_survive_reload(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    entry = make_entry(F1)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(CONTROL).state == "off"
    assert hass.states.get(STATUS).state == "dry_run"

    await hass.services.async_call("switch", "turn_on", {"entity_id": CONTROL}, blocking=True)
    assert hass.states.get(STATUS).state == "ok"

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(CONTROL).state == "on"


async def test_boiler_without_cooling_hides_cool(hass: HomeAssistant, make_entry) -> None:
    options = {
        "mode": {"capabilities": ["heat"]},
        "fallback": {"kind": "none"},
        "weather": {},
    }
    entry = make_entry(GF, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(OVERRIDE).attributes["options"] == ["auto", "heat", "off"]
    assert hass.states.get(MODE).state == "off"


async def test_circuit_device_hangs_under_house(hass: HomeAssistant, make_entry, caplog) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    entry = make_entry(F1)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    house = registry.async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    circuit_id = next(iter(entry.subentries))
    circuit = registry.async_get_device_by_identifier((DOMAIN, circuit_id), entry.entry_id)
    assert circuit.via_device_id == house.id
    assert "via_device" not in caplog.text


async def test_mode_details_show_sources(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "unavailable")
    hass.states.async_set(TANK, "35", {"friendly_name": "Tank", "unit_of_measurement": "°C"})
    hass.states.async_set(
        "sensor.hot_water", "45.0", {"friendly_name": "Hot water", "unit_of_measurement": "°C"}
    )
    await _setup(hass, make_entry, F1)

    attributes = hass.states.get(MODE).attributes
    assert attributes["decided_by"] == "Tank"
    assert attributes["source_state"] == "unavailable"
    assert attributes["fallback_temperature"] == 35.0
    assert attributes["heat_threshold"] == 28.0
    assert attributes["Hot water"] == "45.0 °C"

    hass.states.async_set(HEAT_PUMP, "heat", {"hvac_action": "heating"})
    hass.states.async_set(
        "sensor.hot_water",
        "47.5000015258789",
        {"friendly_name": "Hot water", "unit_of_measurement": "°C"},
    )
    await hass.async_block_till_done()
    attributes = hass.states.get(MODE).attributes
    assert attributes["source"] == "entity"
    assert attributes["source_action"] == "heating"
    assert attributes["Hot water"] == "47.5 °C"


async def test_circuit_state_explains_why(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(
        "climate.office",
        "heat",
        {
            "hvac_action": "idle",
            "current_temperature": 22.4,
            "temperature": 22.0,
            "friendly_name": "Office",
        },
    )
    hass.states.async_set(
        "climate.kitchen",
        "off",
        {
            "hvac_action": "off",
            "current_temperature": 20.0,
            "temperature": 21.0,
            "friendly_name": "Kitchen",
        },
    )
    await _setup(hass, make_entry, F1)

    state = hass.states.get("sensor.f1_state")
    assert state.state == "idle"
    assert state.attributes["reason"] == (
        "Not heating – no zone asks for heat: 1 reached target, 1 off"
    )
    assert state.attributes["Office"] == "target reached 22.4 °C / 22.0 °C"
    assert state.attributes["Kitchen"] == "thermostat off"

    hass.states.async_set(
        "climate.office",
        "heat",
        {
            "hvac_action": "heating",
            "current_temperature": 21.0,
            "temperature": 22.0,
            "friendly_name": "Office",
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.f1_state")
    assert state.state == "heating"
    assert state.attributes["reason"] == "Heating – 1 of 2 zones: Office"


async def test_overview_sensors_have_their_own_entities(hass, make_entry) -> None:
    hass.states.async_set(
        "sensor.hot_water",
        "52.5",
        {
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "friendly_name": "Hot water tank",
        },
    )
    entry = make_entry()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.climate_circuits_hot_water_tank")
    assert state.state == "52.5"
    assert state.attributes["unit_of_measurement"] == "°C"
    hass.states.async_set("sensor.hot_water", "50.0", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.climate_circuits_hot_water_tank").state == "50.0"
