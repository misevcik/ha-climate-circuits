"""Config, options and circuit subentry flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.climate_circuits.const import DOMAIN, SUBENTRY_TYPE_CIRCUIT

from .conftest import HOUSE_OPTIONS


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], HOUSE_OPTIONS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["mode"]["capabilities"] == ["heat", "cool"]


async def test_user_flow_requires_fallback_sensor(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    options = {**HOUSE_OPTIONS, "fallback": {"kind": "tank"}}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], options)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "fallback_sensor_required"}


async def test_add_circuit(hass: HomeAssistant, make_entry) -> None:
    entry = make_entry()
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_CIRCUIT), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    data = {
        "name": "F1",
        "zones": {"heating_zones": ["climate.office"]},
        "heat_curve": {
            "room": 22,
            "design_outdoor": -15,
            "design_supply": 50,
            "exponent": 1.3,
            "minimum": 35,
            "maximum": 50,
            "correction": 0,
        },
        "cool_curve": {"room": 24, "slope": 0.5, "minimum": 16, "maximum": 22, "correction": 0},
        "outputs": {"mixer_open": "switch.open", "travel": 125, "hysteresis": 0.5},
    }
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], data)
    assert result["errors"] == {"base": "mixer_needs_both_relays"}

    data["outputs"] |= {"mixer_close": "switch.close", "supply_sensor": "sensor.supply"}
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], data)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))
    assert subentry.title == "F1"
