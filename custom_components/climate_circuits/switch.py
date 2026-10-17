"""Control equipment (off = dry run) and hot water circulation switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .entity import (
    CircuitEntity,
    HotWaterEntity,
    HouseEntity,
    SourceEntity,
    owner_entity,
    subentry_of,
)
from .tuning import TunableSwitch, set_tuned, tunables, tuned


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
    for owner, values in tunables(house):
        entities = []
        for tunable in values:
            if isinstance(tunable, TunableSwitch):
                entity = owner_entity(owner, TunedSwitch, tunable.key)
                entity.tune(owner, tunable.key)
                entities.append(entity)
        if entities:
            async_add_entities(entities, config_subentry_id=subentry_of(owner))
    for source in house.sources.values():
        if source.controllable:
            async_add_entities(
                [SetpointControlSwitch(source, "setpoint_control")], config_subentry_id=source.id
            )


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


class SetpointControlSwitch(SourceEntity, SwitchEntity):
    """Lets the integration set the heat source from the circuits (with Control equipment on)."""

    @property
    def is_on(self) -> bool:
        return self.source.control_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.source.set_control_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.source.set_control_enabled(False)


class CircuitControlSwitch(CircuitEntity, SwitchEntity):
    """Lets the integration drive this circuit's pump and mixer (with Control equipment on)."""

    @property
    def is_on(self) -> bool:
        return self.circuit.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.circuit.set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.circuit.set_enabled(False)


class TunedSwitch(SwitchEntity):
    """A setting switched on the device; applies at once."""

    _attr_entity_category = EntityCategory.CONFIG

    def tune(self, owner: Any, key: str) -> None:
        self._owner, self._key = owner, key

    @property
    def is_on(self) -> bool:
        return bool(tuned(self._owner, self._key))

    async def async_turn_on(self, **kwargs: Any) -> None:
        set_tuned(self._owner, self._key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        set_tuned(self._owner, self._key, False)
