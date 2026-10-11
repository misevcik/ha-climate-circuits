"""Control equipment (off = dry run) and hot water circulation switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .entity import CircuitEntity, HotWaterEntity, HouseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    house = entry.runtime_data
    async_add_entities([ControlEquipmentSwitch(house, "control_equipment")])
    for circuit in house.circuits.values():
        if circuit.pump or circuit.mixer:
            async_add_entities(
                [CircuitControlSwitch(circuit, "circuit_control")], config_subentry_id=circuit.id
            )
    if house.hot_water:
        async_add_entities([CirculationSwitch(house.hot_water, "circulation_enabled")])


class ControlEquipmentSwitch(HouseEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return self.house.control_equipment

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.house.set_control_equipment(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.house.set_control_equipment(False)


class CirculationSwitch(HotWaterEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        return self.hot_water.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.hot_water.set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.hot_water.set_enabled(False)


class CircuitControlSwitch(CircuitEntity, SwitchEntity):
    """Lets the integration drive this circuit's pump and mixer (with Control equipment on)."""

    @property
    def is_on(self) -> bool:
        return self.circuit.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.circuit.set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.circuit.set_enabled(False)
