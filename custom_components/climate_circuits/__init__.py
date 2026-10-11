"""Climate Circuits: hydronic heating and cooling circuits for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .card import async_register_card
from .const import DOMAIN, SUBENTRY_TYPE_CIRCUIT
from .entity import device_info
from .house import Circuit, House

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type ClimateCircuitsConfigEntry = ConfigEntry[House]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ClimateCircuitsConfigEntry) -> bool:
    house = entry.runtime_data = House(hass, entry)
    await house.async_load()
    # Circuit devices hang under the house device, which must exist first.
    house.device_id = (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id, **device_info(entry.entry_id, "Climate Circuits")
        )
        .id
    )
    for subentry in entry.get_subentries_of_type(SUBENTRY_TYPE_CIRCUIT):
        house.circuits[subentry.subentry_id] = Circuit(house, subentry)
    house.evaluate()  # before the entities exist, so none starts with a wrong state
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    house.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ClimateCircuitsConfigEntry) -> bool:
    await entry.runtime_data.async_unload()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ClimateCircuitsConfigEntry) -> None:
    if not entry.runtime_data.apply_tuning_changes():
        await hass.config_entries.async_reload(entry.entry_id)
