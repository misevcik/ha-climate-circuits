"""Heat sources: their own subentry and device, chosen by the circuits."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.climate_circuits.const import SUBENTRY_TYPE_CIRCUIT, SUBENTRY_TYPE_SOURCE

from .conftest import circuit_data, source_data

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
