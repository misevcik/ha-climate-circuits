"""Base entities: one device for the house, one per circuit and source, one for hot water."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .circuit import Circuit
from .const import DOMAIN
from .hot_water import HotWater
from .house import House
from .listeners import Listeners
from .source import Source


def device_info(identifier: str, name: str, via: str | None = None) -> DeviceInfo:
    info = DeviceInfo(
        identifiers={(DOMAIN, identifier)}, name=name, entry_type=DeviceEntryType.SERVICE
    )
    if via:
        info["via_device_id"] = via
    return info


class _Entity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, source: Listeners, prefix: str, key: str, device: DeviceInfo) -> None:
        self._source = source
        self._attr_unique_id = f"{prefix}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = device

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._source.async_add_listener(self.async_write_ha_state))


class HouseEntity(_Entity):
    def __init__(self, house: House, key: str) -> None:
        self.house = house
        entry_id = house.entry.entry_id
        super().__init__(house, entry_id, key, device_info(entry_id, "Climate Circuits"))


class CircuitEntity(_Entity):
    def __init__(self, circuit: Circuit, key: str) -> None:
        self.circuit = circuit
        device = device_info(circuit.id, circuit.name, circuit.house.device_id)
        super().__init__(circuit, circuit.id, key, device)


class HotWaterEntity(_Entity):
    def __init__(self, hot_water: HotWater, key: str) -> None:
        self.hot_water = hot_water
        device = device_info(hot_water.id, "Hot water", hot_water.house.device_id)
        super().__init__(hot_water, hot_water.id, key, device)


class SourceEntity(_Entity):
    def __init__(self, source: Source, key: str) -> None:
        self.source = source
        device = device_info(source.id, source.name, source.house.device_id)
        super().__init__(source, source.id, key, device)
