"""Mode, status, circuit state, target water and circulation sensors; the set_curve service."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_platform, entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ClimateCircuitsConfigEntry
from .activity import log_activity
from .const import (
    CIRCUIT_STATES,
    CIRCULATION_STATES,
    DEFAULT_COOL_CURVE,
    DEFAULT_HEAT_CURVE,
    DOMAIN,
    MIXER_STATES,
    SERVICE_SET_CURVE,
    STATUSES,
)
from .core.circulation import CirculationReason
from .core.mode import Mode
from .core.texts import (
    change_message,
    circuit_reason,
    circulation_message,
    curve_parameter_label,
    zone_text,
)
from .entity import CircuitEntity, HotWaterEntity, HouseEntity, SourceEntity
from .house import House
from .schema_layout import schema_layout
from .states import number, state_of

_TEMP = vol.All(vol.Coerce(float), vol.Range(min=-40, max=90))
SET_CURVE_SCHEMA = {
    vol.Required("mode"): vol.In(["heat", "cool"]),
    vol.Optional("room"): vol.All(vol.Coerce(float), vol.Range(min=5, max=35)),
    vol.Optional("design_outdoor"): _TEMP,
    vol.Optional("design_supply"): _TEMP,
    vol.Optional("exponent"): vol.All(vol.Coerce(float), vol.Range(min=1, max=2)),
    vol.Optional("slope"): vol.All(vol.Coerce(float), vol.Range(min=0, max=5)),
    vol.Optional("minimum"): _TEMP,
    vol.Optional("maximum"): _TEMP,
    vol.Optional("correction"): vol.All(vol.Coerce(float), vol.Range(min=-10, max=10)),
}
_CURVES = {"heat": DEFAULT_HEAT_CURVE, "cool": DEFAULT_COOL_CURVE}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClimateCircuitsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    entity_platform.async_get_current_platform().async_register_entity_service(
        SERVICE_SET_CURVE, SET_CURVE_SCHEMA, "async_set_curve"
    )
    house = entry.runtime_data
    async_add_entities([ModeSensor(house, "mode"), StatusSensor(house, "status")])
    async_add_entities([InfoSensor(house, entity_id) for entity_id in house.settings.info_sensors])
    if house.hot_water:
        async_add_entities(
            [
                CirculationSensor(house.hot_water, "circulation"),
                CirculationTemperatureSensor(house.hot_water, "circulation_temperature"),
            ]
        )
    for source in house.sources.values():
        source_entities: list[SensorEntity] = [
            SourceTemperatureSensor(source, "source_temperature")
        ]
        if source.settings.setpoint_entity:
            source_entities.append(SourceSetpointSensor(source, "source_setpoint"))
        async_add_entities(source_entities, config_subentry_id=source.id)
    for circuit in house.circuits.values():
        entities: list[SensorEntity] = [
            CircuitStateSensor(circuit, "state"),
            TargetWaterSensor(circuit, "target_water_temperature"),
            CallingZonesSensor(circuit, "calling_zones"),
        ]
        if circuit.mixer or circuit.settings.mixer_position:
            entities.append(MixerPositionSensor(circuit, "mixer_position"))
        if circuit.mixer:
            entities.append(MixerStateSensor(circuit, "mixer_state"))
        async_add_entities(entities, config_subentry_id=circuit.id)


def _invalid(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders
    )


class ModeSensor(HouseEntity, SensorEntity):
    """The house mode; its layout attribute feeds the schema card."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [m.value for m in Mode]
    _unrecorded_attributes = frozenset({"layout"})

    @property
    def native_value(self) -> str:
        return self.house.mode.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.house.mode_details() | {"layout": schema_layout(self.house)}


class InfoSensor(HouseEntity, SensorEntity):
    """An overview sensor (Display section) shown on the house device with its own name."""

    def __init__(self, house: House, entity_id: str) -> None:
        super().__init__(house, f"info_{entity_id}")
        self._attr_translation_key = None
        self._source_entity = entity_id
        registered = er.async_get(house.hass).async_get(entity_id)
        state = house.hass.states.get(entity_id)
        self._attr_name = (
            (registered and (registered.name or registered.original_name))
            or (state and state.name)
            or entity_id
        )

    def _number(self) -> float | None:
        state = state_of(self.hass, self._source_entity)
        return number(state.state) if state else None

    @property
    def native_value(self) -> float | str | None:
        if (state := state_of(self.hass, self._source_entity)) is None:
            return None
        value = number(state.state)
        return value if value is not None else state.state

    @property
    def native_unit_of_measurement(self) -> str | None:
        state = self.hass.states.get(self._source_entity)
        return state.attributes.get("unit_of_measurement") if state else None

    @property
    def device_class(self) -> SensorDeviceClass | None:
        state = self.hass.states.get(self._source_entity)
        if state is None or self._number() is None:
            return None
        try:
            return SensorDeviceClass(state.attributes.get("device_class"))
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"entity": self._source_entity}


class StatusSensor(HouseEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES

    @property
    def native_value(self) -> str:
        return self.house.status


class TargetWaterSensor(CircuitEntity, SensorEntity):
    """Target supply temperature; its attributes feed the curve card."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        return target.value if (target := self.circuit.target) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        circuit, s = self.circuit, self.circuit.settings
        dew = circuit.dew_point
        return {
            "reason": circuit.target.reason if circuit.target else "mode off",
            "dew_point": round(dew, 1) if dew is not None else None,
            "outdoor_temperature": circuit.house.outdoor,
            "house_mode": circuit.house.mode.value,
            "source_headroom": (
                round(headroom, 1) if (headroom := circuit.source_headroom()) is not None else None
            ),
            "heat_curve": {key: getattr(s.heat_curve, key) for key in DEFAULT_HEAT_CURVE},
            "cool_curve": {key: getattr(s.cool_curve, key) for key in DEFAULT_COOL_CURVE},
        }

    async def async_set_curve(self, mode: str, **values: float) -> None:
        """Write to the circuit subentry (applied without reload) and log to Activity."""
        section, defaults = f"{mode}_curve", _CURVES[mode]
        if unknown := set(values) - set(defaults):
            raise _invalid("curve_unknown_parameter", parameters=", ".join(sorted(unknown)))
        entry = self.circuit.house.entry
        subentry = entry.subentries[self.circuit.id]
        old = {**defaults, **subentry.data.get(section, {})}
        curve = {**old, **values}
        if curve["minimum"] > curve["maximum"]:
            raise _invalid("curve_min_above_max")
        if mode == "heat" and curve["design_outdoor"] >= curve["room"]:
            raise _invalid("design_outdoor_above_room")
        self.hass.config_entries.async_update_subentry(
            entry, subentry, data={**subentry.data, section: curve}
        )
        for key, value in values.items():
            if old[key] != value:
                label = curve_parameter_label(mode, key, self.hass.config.language)
                message = change_message(label, float(old[key]), value)
                log_activity(self.hass, self.circuit.name, message, self.entity_id)


class CircuitStateSensor(CircuitEntity, SensorEntity):
    """Heating / cooling / idle / off, the reason and one line per zone."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = CIRCUIT_STATES

    @property
    def native_value(self) -> str | None:
        return e.state.value if (e := self.circuit.explanation) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if (e := self.circuit.explanation) is None:
            return {}
        language = self.hass.config.language
        reason = circuit_reason(e, language, self.circuit.house.decision.reason)
        return {"reason": reason} | {z.zone.name: zone_text(z, e.mode, language) for z in e.zones}


class CirculationSensor(HotWaterEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = CIRCULATION_STATES

    @property
    def native_value(self) -> str | None:
        if (d := self.hot_water.decision) is None:
            return None
        if d.reason is CirculationReason.DISABLED:
            return "disabled"
        if d.reason is CirculationReason.NO_SENSOR:
            return "unavailable"
        return "running" if d.on else "stopped"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        hot_water, house = self.hot_water, self.hot_water.house
        if (d := hot_water.decision) is None:
            return {}
        language = self.hass.config.language
        return {
            "reason": circulation_message(d, language, dry_run=not house.control_equipment),
            "temperature": round(d.temperature, 1) if d.temperature is not None else None,
            "starts_below": d.on_below,
            "stops_at": d.off_at,
            "pump": hot_water.settings.pump,
            "pump_on": hot_water.pump_state(),
            "controlled": house.control_equipment,
        }


class CirculationTemperatureSensor(HotWaterEntity, SensorEntity):
    """The circulation return temperature the pump decides on."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        return d.temperature if (d := self.hot_water.decision) else None


class SourceTemperatureSensor(SourceEntity, SensorEntity):
    """The water the heat source gives the circuits."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        return self.source.temperature()


class SourceSetpointSensor(SourceEntity, SensorEntity):
    """What the heat source is set to give (the heat pump's target for the tank)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        return self.source.setpoint()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.source.setpoint_decision
        return {
            "entity": self.source.settings.setpoint_entity,
            "wanted": d.wanted if d else None,
            "wanted_reason": d.reason if d else None,
            "warmest_circuit": d.circuit if d else None,
            "warmest_target": d.target if d else None,
            "margin": self.source.margin,
            "paused_until": self.source.paused_until,
            "controlled": self.source.control_enabled and self.source.house.control_equipment,
        }


class CallingZonesSensor(CircuitEntity, SensorEntity):
    """Names of the thermostats heating or cooling now, "–" when none."""

    _attr_icon = "mdi:thermostat"

    @property
    def native_value(self) -> str | None:
        if (e := self.circuit.explanation) is None:
            return None
        return (", ".join(z.zone.name for z in e.calling) or "–")[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        e = self.circuit.explanation
        calling = [z.zone.entity_id for z in e.calling] if e else []
        return {"count": len(calling), "zones": calling}


class MixerPositionSensor(CircuitEntity, SensorEntity):
    """How far the mixing valve is open, with the supply temperature it gives."""

    _attr_icon = "mdi:valve"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> float | None:
        return self.circuit.mixer_position()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        supply, target = self.circuit.supply_temperature(), self.circuit.target
        source = self.circuit.source_temperature()
        return {
            "supply_temperature": round(supply, 1) if supply is not None else None,
            "source_temperature": round(source, 1) if source is not None else None,
            "target_temperature": target.value if target else None,
            "source": "integration" if self.circuit.mixer else self.circuit.settings.mixer_position,
        } | (self.circuit.mixer.details() if self.circuit.mixer else {})


class MixerStateSensor(CircuitEntity, SensorEntity):
    """What the mixing valve is doing: idle, opening, closing, homing."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = MIXER_STATES
    _attr_icon = "mdi:valve"

    @property
    def native_value(self) -> str | None:
        return self.circuit.mixer.status() if self.circuit.mixer else None
