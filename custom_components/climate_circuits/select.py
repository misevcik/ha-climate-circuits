"""Manual mode override; modes the source cannot deliver are not offered."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .core.mode import Mode, Override
from .entity import HouseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([OverrideSelect(entry.runtime_data, "mode_override")])


class OverrideSelect(HouseEntity, SelectEntity):
    @property
    def options(self) -> list[str]:
        capable = self.house.settings.mode.capabilities
        return [
            o.value for o in Override if o in (Override.AUTO, Override.OFF) or Mode(o) in capable
        ]

    @property
    def current_option(self) -> str:
        return self.house.override.value

    async def async_select_option(self, option: str) -> None:
        self.house.set_override(Override(option))
