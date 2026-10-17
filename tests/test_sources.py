"""Heat sources: their own subentry and device, chosen by the circuits."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.climate_circuits.const import (
    EVENT_ACTIVITY,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_SOURCE,
)

from .conftest import HEAT_PUMP, OUTDOOR, circuit_data, set_thermostat, source_data

TANK_TOP = "sensor.tank_top"
BOILER = "sensor.boiler_supply"


async def _setup(hass: HomeAssistant, make_entry, *subentries):
    hass.states.async_set(TANK_TOP, "45.5", {"unit_of_measurement": "°C"})
    hass.states.async_set(BOILER, "60.0", {"unit_of_measurement": "°C"})
    entry = make_entry(*subentries)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_add_heat_source(hass: HomeAssistant, make_entry) -> None:
    entry = make_entry()
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_SOURCE), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Buffer tank", "temperature_sensor": TANK_TOP}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert next(iter(entry.subentries.values())).title == "Buffer tank"


async def test_circuit_form_offers_the_heat_sources(hass: HomeAssistant, make_entry) -> None:
    entry = make_entry(source_data("Buffer tank", TANK_TOP))
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_CIRCUIT), context={"source": SOURCE_USER}
    )
    outputs = next(f for f in result["data_schema"].schema if str(f) == "outputs")
    fields = {str(k): v for k, v in result["data_schema"].schema[outputs].schema.schema.items()}
    options = fields["source"].config["options"]
    assert [o["label"] for o in options] == ["Buffer tank"]


async def test_source_has_its_temperature_entity(hass: HomeAssistant, make_entry) -> None:
    await _setup(hass, make_entry, source_data("Buffer tank", TANK_TOP))
    assert hass.states.get("sensor.buffer_tank_temperature").state == "45.5"


async def test_only_source_is_used_by_every_circuit(hass: HomeAssistant, make_entry) -> None:
    entry = await _setup(hass, make_entry, source_data("Buffer tank", TANK_TOP), circuit_data("F1"))
    circuit = next(iter(entry.runtime_data.circuits.values()))
    assert circuit.source_temperature() == 45.5


async def test_with_two_sources_the_circuit_uses_the_chosen_one(
    hass: HomeAssistant, make_entry
) -> None:
    entry = await _setup(
        hass,
        make_entry,
        source_data("Buffer tank", TANK_TOP),
        source_data("Boiler", BOILER),
        circuit_data("F1"),
    )
    house = entry.runtime_data
    circuit = next(iter(house.circuits.values()))
    assert circuit.source_temperature() is None  # two sources, none chosen
    boiler = next(s for s in house.sources.values() if s.name == "Boiler")
    circuit.settings = circuit.settings.__class__(
        **{
            **{f: getattr(circuit.settings, f) for f in circuit.settings.__slots__},
            "source": boiler.id,
        }
    )
    assert circuit.source_temperature() == 60.0


HEAT_PUMP_TARGET = "climate.heat_pump_target"


async def test_set_temperature_and_a_warning_when_too_low(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(OUTDOOR, "0.0")
    hass.states.async_set(HEAT_PUMP_TARGET, "heat", {"temperature": 30.0})
    set_thermostat(hass, "climate.room", "heating")
    events = async_capture_events(hass, EVENT_ACTIVITY)
    source = source_data("Buffer tank", TANK_TOP)
    source["data"]["setpoint_entity"] = HEAT_PUMP_TARGET
    await _setup(
        hass, make_entry, source, circuit_data("F1", zones={"heating_zones": ["climate.room"]})
    )
    assert hass.states.get("sensor.buffer_tank_set_temperature").state == "30.0"
    assert any("is set to 30.0 °C" in e.data["message"] for e in events)
    hass.states.async_set(HEAT_PUMP_TARGET, "heat", {"temperature": 60.0})
    await hass.async_block_till_done()
    assert any("covers the" in e.data["message"] for e in events)


async def test_schema_card_gets_the_heat_generator_only_when_set(
    hass: HomeAssistant, make_entry
) -> None:
    heated = source_data("Buffer tank", TANK_TOP)
    heated["data"] |= {"heater_name": "Heat pump", "heater_supply": "sensor.hp_out"}
    await _setup(hass, make_entry, heated, source_data("Boiler", BOILER))
    tank, boiler = hass.states.get("sensor.climate_circuits_mode").attributes["layout"]["sources"]
    assert tank["heater"] == {"name": "Heat pump", "supply": "sensor.hp_out", "return": None}
    assert boiler["heater"] is None


async def test_source_is_set_from_the_circuits_only_when_switched_on(
    hass: HomeAssistant, make_entry
) -> None:
    calls: list[dict] = []

    async def set_temperature(call) -> None:
        calls.append(dict(call.data))

    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(OUTDOOR, "0.0")
    hass.states.async_set(
        HEAT_PUMP_TARGET, "heat", {"temperature": 45.0, "min_temp": 20, "max_temp": 60}
    )
    set_thermostat(hass, "climate.room", "heating")
    events = async_capture_events(hass, EVENT_ACTIVITY)
    source = source_data("Buffer tank", TANK_TOP)
    source["data"] |= {"setpoint_entity": HEAT_PUMP_TARGET, "setpoint_margin": 5.0}
    entry = await _setup(
        hass, make_entry, source, circuit_data("F1", zones={"heating_zones": ["climate.room"]})
    )
    # After the setup: the climate platform brings the real climate services.
    hass.services.async_register("climate", "set_temperature", set_temperature)
    house = entry.runtime_data
    target = float(hass.states.get("sensor.f1_target_water_temperature").state)
    wanted = float(int(target + 5.0) + (0 if (target + 5.0).is_integer() else 1))
    attrs = hass.states.get("sensor.buffer_tank_set_temperature").attributes
    assert attrs["wanted"] == wanted and attrs["controlled"] is False
    assert calls == []  # the switch is off

    switch = "switch.buffer_tank_heat_pump_controlled_by_integration"
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done()
    assert calls == []  # Control equipment is off: only said in Activity
    assert any(
        "setting it to" in e.data["message"] and "dry run" in e.data["message"] for e in events
    )

    house.set_control_equipment(True)
    await hass.async_block_till_done()
    assert calls == [{"entity_id": HEAT_PUMP_TARGET, "temperature": wanted}]


async def _heat_pump_house(hass: HomeAssistant, make_entry, calls: list[dict]):
    async def set_temperature(call) -> None:
        calls.append(dict(call.data))
        hass.states.async_set(
            HEAT_PUMP_TARGET,
            "heat",
            {"temperature": call.data["temperature"], "min_temp": 20, "max_temp": 60},
        )

    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(OUTDOOR, "0.0")
    hass.states.async_set(
        HEAT_PUMP_TARGET, "heat", {"temperature": 45.0, "min_temp": 20, "max_temp": 60}
    )
    set_thermostat(hass, "climate.room", "heating")
    source = source_data("Buffer tank", TANK_TOP)
    source["data"] |= {"setpoint_entity": HEAT_PUMP_TARGET}
    entry = await _setup(
        hass, make_entry, source, circuit_data("F1", zones={"heating_zones": ["climate.room"]})
    )
    # After the setup: the climate platform brings the real climate services.
    hass.services.async_register("climate", "set_temperature", set_temperature)
    house = entry.runtime_data
    house.set_control_equipment(True)
    switch = "switch.buffer_tank_heat_pump_controlled_by_integration"
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done()
    return house


async def test_a_change_by_hand_pauses_the_automatic_setting(
    hass: HomeAssistant, make_entry
) -> None:
    calls: list[dict] = []
    events = async_capture_events(hass, EVENT_ACTIVITY)
    house = await _heat_pump_house(hass, make_entry, calls)
    source = next(iter(house.sources.values()))
    assert len(calls) == 1 and source.margin == 8.0  # set once, nothing seen as by hand
    assert source.paused_until is None

    hass.states.async_set(
        HEAT_PUMP_TARGET, "heat", {"temperature": 50.0, "min_temp": 20, "max_temp": 60}
    )
    await hass.async_block_till_done()
    assert any("changed by hand to 50.0" in e.data["message"] for e in events)
    assert source.paused_until is not None
    source._changed_at = None  # no waiting for the 15 min between changes
    house.evaluate()
    await hass.async_block_till_done()
    assert len(calls) == 1  # paused

    wall = house.wall()
    house.wall = lambda: wall + 61  # the pause after a change by hand is 1 min by default
    house.evaluate()
    await hass.async_block_till_done()
    assert len(calls) == 2  # set again after the pause
    assert any("pause after a change by hand is over" in e.data["message"] for e in events)


async def test_margin_learns_and_can_be_set_by_hand(hass: HomeAssistant, make_entry) -> None:
    calls: list[dict] = []
    house = await _heat_pump_house(hass, make_entry, calls)
    source = next(iter(house.sources.values()))
    circuit = next(iter(house.circuits.values()))

    class Mixer:
        starved = True
        params = type("P", (), {"hysteresis": 0.5})()

        def position(self) -> float:
            return 100.0

    circuit.mixer = Mixer()
    house.evaluate()
    await hass.async_block_till_done()
    assert source.margin == 9.0

    margin = "number.buffer_tank_margin_above_the_warmest_circuit"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": margin, "value": 6}, blocking=True
    )
    assert source.margin == 6.0
    assert hass.states.get(margin).state == "6.0"
    mode = "select.buffer_tank_margin"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": mode, "option": "manual"}, blocking=True
    )
    source._margin_changed_at = None  # learning would be allowed again by now
    house.evaluate()
    await hass.async_block_till_done()
    assert source.margin == 6.0  # manual: the value set by hand holds, the mixer still short
    await hass.services.async_call(
        "select", "select_option", {"entity_id": mode, "option": "auto"}, blocking=True
    )
    source._margin_changed_at = None
    house.evaluate()
    await hass.async_block_till_done()
    assert source.margin == 7.0  # auto again: learns on from the value set by hand
    (card,) = hass.states.get("sensor.climate_circuits_mode").attributes["layout"]["sources"]
    assert card["setpoint_control"] == "switch.buffer_tank_heat_pump_controlled_by_integration"
    assert card["margin"] == margin
    assert card["margin_mode"] == mode


async def test_the_heat_pump_shows_on_the_source_and_a_change_there_counts_as_by_hand(
    hass: HomeAssistant, make_entry
) -> None:
    calls: list[dict] = []
    house = await _heat_pump_house(hass, make_entry, calls)
    source = next(iter(house.sources.values()))
    mirror = "climate.buffer_tank_heat_generator"
    state = hass.states.get(mirror)
    assert state.state == "heat"
    assert state.attributes["temperature"] == calls[-1]["temperature"]
    assert state.attributes["entity"] == HEAT_PUMP_TARGET

    # The climate service is replaced by the test's heat pump, so the entity is called directly.
    entity = hass.data["entity_components"]["climate"].get_entity(mirror)
    await entity.async_set_temperature(temperature=52)
    await hass.async_block_till_done()
    assert calls[-1] == {"entity_id": HEAT_PUMP_TARGET, "temperature": 52}
    assert hass.states.get(mirror).attributes["temperature"] == 52
    assert source.paused_until is not None  # a change by hand


async def test_limits_are_numbers_on_the_source_and_keep_their_order(
    hass: HomeAssistant, make_entry
) -> None:
    calls: list[dict] = []
    house = await _heat_pump_house(hass, make_entry, calls)
    lowest, highest = "number.buffer_tank_lowest_setting", "number.buffer_tank_highest_setting"
    assert hass.states.get(lowest).state == "30.0" and hass.states.get(highest).state == "55.0"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": lowest, "value": 60}, blocking=True
        )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": highest, "value": 40}, blocking=True
    )
    await hass.async_block_till_done()
    assert next(iter(house.sources.values())).setpoint_decision.wanted <= 40
    pause = "number.buffer_tank_pause_after_a_change_by_hand"
    assert hass.states.get(pause).state == "1.0"
    linked = hass.states.get("sensor.buffer_tank_set_temperature_from")
    assert linked.attributes["entity_id"] == HEAT_PUMP_TARGET
