"""The heat pump (or boiler) a heat source is set on, shown on the source's device.

It mirrors the climate entity chosen as the source's set temperature, so the device shows what
it is linked to. A change made here goes to that entity, and counts as a change by hand: the
automatic setting from the circuits pauses.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .entity import SourceEntity
from .source import Source
from .states import number, state_of


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for source in entry.runtime_data.sources.values():
        entity = source.settings.setpoint_entity
        if entity and entity.startswith("climate."):
            async_add_entities(
                [HeatGenerator(source, "heat_generator")], config_subentry_id=source.id
            )


class HeatGenerator(SourceEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(self, source: Source, key: str) -> None:
        super().__init__(source, key)
        if source.settings.heater_name:
            self._attr_name = source.settings.heater_name

    @property
    def _linked(self) -> State | None:
        return state_of(self.hass, self.source.settings.setpoint_entity)

    @property
    def available(self) -> bool:
        return self._linked is not None

    def _attr(self, key: str) -> Any:
        state = self._linked
        return state.attributes.get(key) if state else None

    @property
    def hvac_mode(self) -> HVACMode | None:
        state = self._linked
        try:
            return HVACMode(state.state) if state else None
        except ValueError:
            return None

    @property
    def hvac_modes(self) -> list[HVACMode]:
        modes = []
        for mode in self._attr("hvac_modes") or []:
            try:
                modes.append(HVACMode(mode))
            except ValueError:
                continue
        return modes

    @property
    def hvac_action(self) -> HVACAction | None:
        try:
            return HVACAction(self._attr("hvac_action"))
        except ValueError:
            return None

    @property
    def target_temperature(self) -> float | None:
        return number(self._attr(ATTR_TEMPERATURE))

    @property
    def current_temperature(self) -> float | None:
        """The heat pump's own reading, else the water the source gives the circuits."""
        return number(self._attr("current_temperature")) or self.source.temperature()

    @property
    def min_temp(self) -> float:
        return number(self._attr("min_temp")) or super().min_temp

    @property
    def max_temp(self) -> float:
        return number(self._attr("max_temp")) or super().max_temp

    @property
    def target_temperature_step(self) -> float | None:
        return number(self._attr("target_temp_step"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        source = self.source
        return {
            "entity": source.settings.setpoint_entity,
            "controlled_by_integration": source.control_enabled,
            "paused_until": source.paused_until,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": self.source.settings.setpoint_entity, ATTR_TEMPERATURE: temperature},
            blocking=True,
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": self.source.settings.setpoint_entity, "hvac_mode": hvac_mode},
            blocking=True,
        )
