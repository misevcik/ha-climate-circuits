"""A heat source (buffer tank, boiler, heat pump): the water it gives the circuits, and
optionally its setting from the circuits.

The weather curve of each circuit says how warm the water after its mixer should be. The heat
pump is asked for that water plus a reserve: with its own switch and Control equipment on,
the source is set to

    warmest heating circuit target + reserve

A change of the setting by somebody else (the heat pump's app) pauses the automatic setting
for a while. Hot water heating and defrosts are recognised and shown, they do not change it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import callback

from .const import CONTROLLABLE_SETPOINTS, DEFROST_GAP, HOT_WATER_HYSTERESIS, SETPOINT_INTERVAL
from .core.mode import Mode
from .core.setpoint import SetpointDecision, SetpointSettings, setpoint_decision
from .core.texts import setpoint_event_text, setpoint_text
from .listeners import Listeners
from .settings import SourceSettings
from .states import call_service, float_of, number, state_of
from .tuning import tuned

if TYPE_CHECKING:
    from .circuit import Circuit
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
        self._written: float | None = None  # what we set it to, to tell a change by hand
        self._seen: float | None = None  # the setting at the last look
        self._proposed: float | None = None  # dry run: the last value said in Activity
        self._was_paused = False
        self.hot_water_heating: bool | None = None  # None: cannot tell
        self.defrosting: bool | None = None

    @property
    def name(self) -> str:
        return self.settings.name

    @property
    def _stored(self) -> dict[str, Any]:
        return self.house.persisted["sources"].setdefault(self.id, {})

    @property
    def controllable(self) -> bool:
        """Its setting can be written: a climate's target or a number."""
        entity = self.settings.setpoint_entity
        return bool(entity) and entity.split(".")[0] in CONTROLLABLE_SETPOINTS

    @property
    def control_enabled(self) -> bool:
        return bool(self._stored.get("setpoint_control", False))

    @callback
    def set_control_enabled(self, enabled: bool) -> None:
        self._stored["setpoint_control"] = enabled
        self.house.save()
        self.house.evaluate()

    @property
    def reserve(self) -> float:
        return float(tuned(self, "reserve"))

    @property
    def paused_until(self) -> datetime | None:
        """Paused after the setting was changed by hand, until this time."""
        until = self._stored.get("paused_until")
        if until is None or until <= self.house.wall():
            return None
        return datetime.fromtimestamp(until).astimezone()

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
        lowest, highest = tuned(self, "setpoint_min"), tuned(self, "setpoint_max")
        return SetpointSettings(
            reserve=self.reserve,
            minimum=max(lowest, low) if low is not None else lowest,
            maximum=min(highest, high) if high is not None else highest,
            step=step,
            threshold=max(1.0, step),
            interval=SETPOINT_INTERVAL,
        )

    @callback
    def evaluate_setpoint(self, mode: Mode) -> None:
        """After the circuits: set the source; then its entities."""
        if self.controllable:
            self._set_from_circuits(mode)
        self._notify()

    def _set_from_circuits(self, mode: Mode) -> None:
        house = self.house
        current = self.setpoint()
        live = self.control_enabled and house.control_equipment
        self._watch_change_by_hand(current, live)
        paused = self.paused_until is not None
        self._log_resume(paused)
        heating = self._heating_circuits() if mode is Mode.HEAT else []
        decision = self.setpoint_decision = setpoint_decision(
            heating=mode is Mode.HEAT,
            targets={c.name: c.target.value for c in heating if c.target is not None},
            current=current,
            since_change=None if self._changed_at is None else house.now() - self._changed_at,
            settings=self._limits(),
        )
        if not self.control_enabled or paused or not decision.change or decision.wanted is None:
            return
        if not live and decision.wanted == self._proposed:
            return  # dry run: said once per value
        self._log_setpoint(decision, current, dry_run=not live)
        if live:
            self._write_setpoint(decision.wanted)
        self._proposed = None if live else decision.wanted

    def _heating_circuits(self) -> list[Circuit]:
        """The circuits fed by this source that call for heat."""
        return [
            c
            for c in self.house.circuits.values()
            if c.source() is self and c.demand.active and c.target is not None
        ]

    def _watch_change_by_hand(self, current: float | None, live: bool) -> None:
        """A setting we did not write pauses the automatic setting, and a new one extends it."""
        seen, self._seen = self._seen, current
        if not live or current is None or seen is None or abs(current - seen) < 0.1:
            return
        if self._written is not None and abs(current - self._written) < 0.1:
            return  # our own change arriving
        house = self.house
        until = house.wall() + 60 * tuned(self, "manual_pause")
        self._stored["paused_until"] = until
        self._was_paused = True
        house.save()
        self._log_event("manual", value=current, until=datetime.fromtimestamp(until))

    def _log_resume(self, paused: bool) -> None:
        if self._was_paused and not paused:
            self._log_event("resumed")
        self._was_paused = paused

    def _heats_hot_water(self) -> bool | None:
        """From the entity chosen for it, else the heat pump's supply far above the tank.

        Ends a little below the gap it starts at: the two sensors report at different moments.
        """
        s = self.settings
        if s.hot_water_entity:
            state = state_of(self.house.hass, s.hot_water_entity)
            return state.state == "on" if state else None
        supply, tank = float_of(self.house.hass, s.heater_supply), self.temperature()
        if supply is None or tank is None:
            return None
        gap = tuned(self, "hot_water_gap") - (HOT_WATER_HYSTERESIS if self.hot_water_heating else 0)
        return supply - tank >= gap

    def _defrosts(self) -> bool | None:
        """The heat pump reverses to defrost: its supply comes back colder than its return.

        Ends once the supply is back above the return.
        """
        hass, s = self.house.hass, self.settings
        supply, back = float_of(hass, s.heater_supply), float_of(hass, s.heater_return)
        if supply is None or back is None:
            return None
        return supply < back - (0 if self.defrosting else DEFROST_GAP)

    def _watch_heat_generator(self) -> None:
        """Activity when hot water heating or a defrost starts and ends.

        A sensor that drops out for a moment keeps the last state rather than unknown.
        """
        for attr, now, key in (
            ("hot_water_heating", self._heats_hot_water(), "hot_water"),
            ("defrosting", self._defrosts(), "defrost"),
        ):
            was = getattr(self, attr)
            if now is None or now == was:
                continue
            setattr(self, attr, now)
            if was is None:
                continue  # the first look after a start
            self._log_event(f"{key}_on" if now else f"{key}_off")

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
            self.reserve,
            house.hass.config.language,
            dry_run=dry_run,
        )
        house.activity(self.name, message, f"{self.id}_source_setpoint")

    def _log_event(self, key: str, **values: Any) -> None:
        house = self.house
        if house.logging:
            message = setpoint_event_text(key, self.name, house.hass.config.language, **values)
            house.activity(self.name, message, f"{self.id}_source_setpoint")

    def _write_setpoint(self, value: float) -> None:
        """A climate's target temperature, or a number's value."""
        self._changed_at = self.house.now()
        self._written = value
        entity = self.settings.setpoint_entity
        domain = entity.split(".")[0]
        if domain == "climate":
            call_service(
                self.house.hass, "climate", "set_temperature", entity_id=entity, temperature=value
            )
        else:
            call_service(self.house.hass, domain, "set_value", entity_id=entity, value=value)

    def linked_entities(self) -> dict[str, Any]:
        """What the source reads and sets, by role: shown on its device."""
        s = self.settings
        return {
            "temperature_sensor": s.temperature_sensor,
            "setpoint_entity": s.setpoint_entity,
            "heater_supply": s.heater_supply,
            "heater_return": s.heater_return,
            "hot_water_entity": s.hot_water_entity,
        }

    def inputs(self) -> set[str]:
        s = self.settings
        return set(
            filter(
                None,
                [
                    s.temperature_sensor,
                    s.setpoint_entity,
                    s.heater_supply,
                    s.heater_return,
                    s.hot_water_entity,
                ],
            )
        )

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
        """Before the circuits: does the heat generator heat hot water or defrost."""
        self._watch_heat_generator()
