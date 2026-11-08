"""Climate Circuits: hydronic heating and cooling circuits for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType

from .card import async_register_card
from .circuit import Circuit
from .const import DOMAIN, SUBENTRY_TYPE_CIRCUIT, SUBENTRY_TYPE_SOURCE
from .entity import device_info
from .house import House
from .source import Source
from .tuning import seed

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
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
    for subentry in entry.get_subentries_of_type(SUBENTRY_TYPE_SOURCE):
        house.sources[subentry.subentry_id] = Source(house, subentry)
    for subentry in entry.get_subentries_of_type(SUBENTRY_TYPE_CIRCUIT):
        house.circuits[subentry.subentry_id] = Circuit(house, subentry)
    _remove_old_setting(hass, house)
    seed(house)
    house.retune()
    house.evaluate()  # before the entities exist, so none starts with a wrong state
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    house.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


# Entities of the older heat source setting: the learned margin (0.1.18–0.1.27) and the
# measured tank drop (0.1.28). The setting is the warmest target + the reserve now.
_OLD_SOURCE_ENTITIES = (
    ("number", "setpoint_margin"),
    ("number", "margin_raise_gap"),
    ("number", "margin_lower_gap"),
    ("number", "manual_drop"),
    ("number", "drop_window"),
    ("select", "margin_mode"),
    ("sensor", "tank_drop"),
)


_OLD_SOURCE_KEYS = ("margin", "margin_mode", "manual_drop", "drop")  # stored with the source


def _remove_old_setting(hass: HomeAssistant, house: House) -> None:
    """Its entities and stored values."""
    registry = er.async_get(hass)
    stored = house.persisted
    for source in house.sources.values():
        for domain, key in _OLD_SOURCE_ENTITIES:
            if old := registry.async_get_entity_id(domain, DOMAIN, f"{source.id}_{key}"):
                registry.async_remove(old)
        for owner, keys in (("sources", _OLD_SOURCE_KEYS), ("tuning", ("drop_window",))):
            values = stored[owner].get(source.id, {})
            for key in keys:
                values.pop(key, None)


async def async_unload_entry(hass: HomeAssistant, entry: ClimateCircuitsConfigEntry) -> bool:
    await entry.runtime_data.async_unload()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ClimateCircuitsConfigEntry) -> None:
    if not entry.runtime_data.apply_tuning_changes():
        await hass.config_entries.async_reload(entry.entry_id)
