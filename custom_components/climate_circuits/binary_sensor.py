"""Demand of each circuit."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .entity import CircuitEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for circuit in entry.runtime_data.circuits.values():
        entities: list[BinarySensorEntity] = [DemandSensor(circuit, "demand")]
        if circuit.pump:
            entities.append(PumpSensor(circuit, "pump"))
        async_add_entities(entities, config_subentry_id=circuit.id)


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
        return self.circuit.pump.relay.is_on() if self.circuit.pump else None

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
