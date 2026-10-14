"""A heat source (buffer tank, boiler, heat pump): the water it gives the circuits, and
optionally its setting from the circuits."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import callback

from .const import CONTROLLABLE_SETPOINTS, SETPOINT_INTERVAL
from .core.mode import Mode
from .core.setpoint import SetpointDecision, SetpointSettings, setpoint_decision
from .core.texts import setpoint_text
from .listeners import Listeners
from .settings import SourceSettings
from .states import call_service, float_of, number, state_of

if TYPE_CHECKING:
    from .house import House


class Source(Listeners):
    """A heat source: the water it gives the circuits."""

    def __init__(self, house: House, subentry: ConfigSubentry) -> None:
        super().__init__()
        self.house = house
        self.id = subentry.subentry_id
        self.settings = SourceSettings.from_data(subentry.data)
        self.setpoint_decision: SetpointDecision | None = None
        self._changed_at: float | None = None  # when the setting was last changed by us
        self._proposed: float | None = None  # dry run: the last value said in Activity

    @property
    def name(self) -> str:
        return self.settings.name

    @property
    def controllable(self) -> bool:
        """Its setting can be written: a climate's target or a number."""
        entity = self.settings.setpoint_entity
        return bool(entity) and entity.split(".")[0] in CONTROLLABLE_SETPOINTS

    @property
    def control_enabled(self) -> bool:
        stored = self.house.persisted["sources"].get(self.id, {})
        return bool(stored.get("setpoint_control", False))

    @callback
    def set_control_enabled(self, enabled: bool) -> None:
        self.house.persisted["sources"].setdefault(self.id, {})["setpoint_control"] = enabled
        self.house.save()
        self.house.evaluate()

    def _limits(self) -> SetpointSettings:
        """The settings, within the range and step the entity itself accepts."""
        s = self.settings
        state = state_of(self.house.hass, s.setpoint_entity)
        attrs = state.attributes if state else {}
        if state is not None and state.domain == "climate":
            low, high = number(attrs.get("min_temp")), number(attrs.get("max_temp"))
            step = number(attrs.get("target_temp_step")) or 1.0
        else:
            low, high = number(attrs.get("min")), number(attrs.get("max"))
            step = number(attrs.get("step")) or 1.0
        return SetpointSettings(
            margin=s.setpoint_margin,
            minimum=max(s.setpoint_min, low) if low is not None else s.setpoint_min,
            maximum=min(s.setpoint_max, high) if high is not None else s.setpoint_max,
            step=step,
            threshold=max(1.0, step),
            interval=SETPOINT_INTERVAL,
        )

    @callback
    def evaluate_setpoint(self, mode: Mode) -> None:
        """Set the source from the warmest water its heating circuits want (when switched on)."""
        if not self.controllable:
            return
        house = self.house
        current = self.setpoint()
        decision = self.setpoint_decision = setpoint_decision(
            heating=mode is Mode.HEAT,
            targets=self._heating_targets(),
            current=current,
            since_change=None if self._changed_at is None else house.now() - self._changed_at,
            settings=self._limits(),
        )
        if not self.control_enabled or not decision.change or decision.wanted is None:
            return
        live = house.control_equipment
        if not live and decision.wanted == self._proposed:
            return  # dry run: said once per value
        self._log_setpoint(decision, current, dry_run=not live)
        if live:
            self._write_setpoint(decision.wanted)
        self._proposed = None if live else decision.wanted

    def _heating_targets(self) -> dict[str, float]:
        """Target water of the circuits fed by this source that call for heat, by name."""
        return {
            c.name: c.target.value
            for c in self.house.circuits.values()
            if c.source() is self and c.demand.active and c.target is not None
        }

    def _log_setpoint(
        self, decision: SetpointDecision, current: float | None, dry_run: bool
    ) -> None:
        house = self.house
        if not house.logging or decision.wanted is None:
            return
        message = setpoint_text(
            self.name,
            decision.wanted,
            current,
            decision.circuit,
            decision.target,
            self.settings.setpoint_margin,
            house.hass.config.language,
            dry_run=dry_run,
        )
        house.activity(self.name, message, f"{self.id}_source_setpoint")

    def _write_setpoint(self, value: float) -> None:
        """A climate's target temperature, or a number's value."""
        self._changed_at = self.house.now()
        entity = self.settings.setpoint_entity
        domain = entity.split(".")[0]
        if domain == "climate":
            call_service(
                self.house.hass, "climate", "set_temperature", entity_id=entity, temperature=value
            )
        else:
            call_service(self.house.hass, domain, "set_value", entity_id=entity, value=value)

    def inputs(self) -> set[str]:
        return set(filter(None, [self.settings.temperature_sensor, self.settings.setpoint_entity]))

    def temperature(self) -> float | None:
        return float_of(self.house.hass, self.settings.temperature_sensor)

    def setpoint(self) -> float | None:
        """What the source is set to give: a climate's target, else the entity's value."""
        if (state := state_of(self.house.hass, self.settings.setpoint_entity)) is None:
            return None
        if state.domain == "climate":
            return number(state.attributes.get("temperature"))
        return number(state.state)

    @callback
    def refresh(self) -> None:
        self._notify()
