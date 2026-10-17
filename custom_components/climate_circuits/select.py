"""Manual mode override (modes the source cannot deliver are not offered); a heat source's
margin: learned or set by hand."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .core.mode import Mode, Override
from .entity import HouseEntity, SourceEntity
from .source import MARGIN_MODES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([OverrideSelect(entry.runtime_data, "mode_override")])
    for source in entry.runtime_data.sources.values():
        if source.controllable:
            async_add_entities(
                [MarginModeSelect(source, "margin_mode")], config_subentry_id=source.id
            )


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


class MarginModeSelect(SourceEntity, SelectEntity):
    """auto: the margin learns from the mixers; manual: the value set by hand holds."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(MARGIN_MODES)

    @property
    def current_option(self) -> str:
        return self.source.margin_mode

    async def async_select_option(self, option: str) -> None:
        self.source.set_margin_mode(option)
