"""Numbers on the devices: thresholds and constants (tuning.py), a heat source's margin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .entity import SourceEntity, owner_entity, subentry_of
from .source import Source
from .tuning import Tunable, set_tuned, tunables, tuned


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    house = entry.runtime_data
    for owner, values in tunables(house):
        entities = []
        for tunable in values:
            if isinstance(tunable, Tunable):
                entity = owner_entity(owner, TunedNumber, tunable.key)
                entity.tune(owner, tunable)
                entities.append(entity)
        async_add_entities(entities, config_subentry_id=subentry_of(owner))
    for source in house.sources.values():
        if source.controllable:
            async_add_entities(
                [SourceMargin(source, "setpoint_margin")], config_subentry_id=source.id
            )


class TunedNumber(NumberEntity):
    """A threshold or constant set on the device; applies at once."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def tune(self, owner: Any, tunable: Tunable) -> None:
        self._owner, self._key = owner, tunable.key
        self._attr_native_min_value = tunable.minimum
        self._attr_native_max_value = tunable.maximum
        self._attr_native_step = tunable.step
        self._attr_native_unit_of_measurement = tunable.unit  # differences too: no device class

    @property
    def native_value(self) -> float | None:
        return tuned(self._owner, self._key)

    async def async_set_native_value(self, value: float) -> None:
        set_tuned(self._owner, self._key, value)


class SourceMargin(SourceEntity, NumberEntity):
    """°C the source is set above the warmest circuit target; learned, and settable by hand."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS  # a difference: no device class
    _attr_native_min_value = 0
    _attr_native_max_value = 20
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, source: Source, key: str) -> None:
        super().__init__(source, key)

    @property
    def native_value(self) -> float:
        return self.source.margin

    async def async_set_native_value(self, value: float) -> None:
        self.source.set_margin(value)
