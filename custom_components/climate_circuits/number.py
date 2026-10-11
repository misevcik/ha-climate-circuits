"""Hot water circulation threshold and delta, stored in the house options."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .activity import log_activity
from .core.texts import change_message, curve_parameter_label
from .entity import HotWaterEntity
from .house import HotWater


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if hot_water := entry.runtime_data.hot_water:
        async_add_entities(
            [
                CirculationNumber(hot_water, "threshold", 20, 60),
                CirculationNumber(hot_water, "delta", 0.5, 10),
            ]
        )


class CirculationNumber(HotWaterEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, hot_water: HotWater, key: str, minimum: float, maximum: float) -> None:
        super().__init__(hot_water, f"circulation_{key}")
        self._key = key
        self._attr_native_min_value, self._attr_native_max_value = minimum, maximum
        if key == "delta":  # a difference: no device class, so it is never unit-converted
            self._attr_device_class = None

    @property
    def native_value(self) -> float:
        return getattr(self.hot_water.settings, self._key)

    async def async_set_native_value(self, value: float) -> None:
        """Applied without reload by the update listener."""
        if (old := self.native_value) == value:
            return
        entry = self.hot_water.house.entry
        section = {**entry.options.get("hot_water", {}), self._key: value}
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, "hot_water": section}
        )
        label = curve_parameter_label("circulation", self._key, self.hass.config.language)
        log_activity(self.hass, "Hot water", change_message(label, old, value), self.entity_id)
