"""Demand, pump and a heat source that is not enough, per circuit."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .entity import CircuitEntity, SourceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for circuit in entry.runtime_data.circuits.values():
        entities: list[BinarySensorEntity] = [DemandSensor(circuit, "demand")]
        if circuit.pump:
            entities.append(PumpSensor(circuit, "pump"))
        if circuit.mixer:
            entities.append(SourceNotEnoughSensor(circuit, "source_not_enough"))
        async_add_entities(entities, config_subentry_id=circuit.id)
    for source in entry.runtime_data.sources.values():
        s = source.settings
        if s.hot_water_entity or s.heater_supply:
            async_add_entities(
                [HotWaterHeatingSensor(source, "hot_water_heating")], config_subentry_id=source.id
            )


class DemandSensor(CircuitEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool:
        return self.circuit.demand.active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        demand = self.circuit.demand
        return {"zones": list(demand.zones), "reason": demand.reason}


class PumpSensor(CircuitEntity, BinarySensorEntity):
    """The circuit pump as the relay reports it; attributes say what the integration wants."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def is_on(self) -> bool | None:
        return self.circuit.pump.relay.shown() if self.circuit.pump else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        pump = self.circuit.pump
        if pump is None or pump.decision is None:
            return {}
        return {
            "reason": pump.text(),
            "wanted": pump.decision.on,
            "controlled": self.circuit.controlling,
            "entity": pump.relay.entity_id,
        }


class SourceNotEnoughSensor(CircuitEntity, BinarySensorEntity):
    """The mixer is fully open and the supply stays below the target: the water is not enough."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        return bool(self.circuit.mixer and self.circuit.mixer.starved)


class HotWaterHeatingSensor(SourceEntity, BinarySensorEntity):
    """The heat generator heats hot water: from the chosen entity, or its supply far above the
    tank. The circuits may be short of water meanwhile."""

    _attr_icon = "mdi:water-boiler"

    @property
    def is_on(self) -> bool | None:
        return self.source.hot_water_heating
