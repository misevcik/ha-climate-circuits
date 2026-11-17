"""Numbers on the devices: thresholds and constants (tuning.py)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .entity import owner_entity, subentry_of
from .tuning import Tunable, set_tuned, tunables, tuned


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    house = entry.runtime_data
    _remove_unused(hass, house)
    for owner, values in tunables(house):
        entities = []
        for tunable in values:
            if isinstance(tunable, Tunable):
                entity = owner_entity(owner, TunedNumber, tunable.key)
                entity.tune(owner, tunable)
                entities.append(entity)
        async_add_entities(entities, config_subentry_id=subentry_of(owner))


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


def _remove_unused(hass: HomeAssistant, house: Any) -> None:
    """Numbers of values no longer offered, e.g. the margin below a tank sensor removed.

    Every number of the entry is a TunedNumber, so any one not offered now is stale.
    """
    wanted = {f"{owner.id}_{t.key}" for owner, values in tunables(house) for t in values}
    registry = er.async_get(hass)
    for entry in er.async_entries_for_config_entry(registry, house.entry.entry_id):
        if entry.domain == "number" and entry.unique_id not in wanted:
            registry.async_remove(entry.entity_id)
