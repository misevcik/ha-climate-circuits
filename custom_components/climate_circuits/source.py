"""A heat source (buffer tank, boiler, heat pump): the water it gives the circuits, and
optionally its setting from the circuits.

The water that reaches the mixers must be at least as warm as the warmest water a heating
circuit wants after its mixer, plus a reserve. The heat pump measures its setting on its own
sensor, and the water at the mixers is colder by the tank's drop (the outlet sits below the
top, and the tank cools until the heat pump starts again). So, with its own switch and
Control equipment on, the source is set to

    warmest circuit target + reserve + tank drop

The tank drop is measured: the setting minus the water at the mixers, over the last hours,
near its worst (90th percentile). Not counted while the heat generator heats hot water or
defrosts, nor while the tank recovers from that, nor just after the setting changed. It can
also be set by hand. A change of the setting by somebody else (the heat pump's app) pauses
the automatic setting for a while.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import callback

from .const import (
    CONTROLLABLE_SETPOINTS,
    DEFAULT_TANK_DROP,
    DEFROST_GAP,
    DROP_SAMPLE_INTERVAL,
    DROP_SETTLE,
    HEAT_GENERATOR_RECOVERY,
    SETPOINT_INTERVAL,
)
from .core.mode import Mode
from .core.setpoint import SetpointDecision, SetpointSettings, setpoint_decision, tank_drop
from .core.texts import setpoint_event_text, setpoint_text
from .listeners import Listeners
from .settings import SourceSettings
from .states import call_service, float_of, number, state_of
from .tuning import tuned

if TYPE_CHECKING:
    from .circuit import Circuit
    from .house import House

DROP_MODES = ("auto", "manual")  # measured, or the value set by hand
FULLY_OPEN = 99.0  # % a mixer at this lets the tank's water straight through


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
        self._busy_ended: float | None = None  # hot water heating or a defrost ended
        self._samples: deque[tuple[float, float]] = deque()  # (time, setting − water)
        self._measured: float | None = None  # the drop from the samples
        self._sampled_at: float | None = None
        self._setting: float | None = None  # the setting the samples are taken against
        self._setting_since: float | None = None

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

    # The tank drop: measured, or set by hand.

    @property
    def drop_mode(self) -> str:
        return str(self._stored.get("margin_mode", "auto"))  # the key of 0.1.20

    @callback
    def set_drop_mode(self, mode: str) -> None:
        self._stored["margin_mode"] = mode
        self.house.save()
        self.house.evaluate()

    @property
    def manual_drop(self) -> float:
        """Set by hand; at first a margin set by hand before 0.1.27, less the reserve."""
        stored = self._stored
        if "manual_drop" in stored:
            return float(stored["manual_drop"])
        if self.drop_mode == "manual" and "margin" in stored:
            return max(float(stored["margin"]) - self.reserve, 0.0)
        return DEFAULT_TANK_DROP

    @callback
    def set_manual_drop(self, drop: float) -> None:
        self._stored["manual_drop"] = drop
        self.house.save()
        self.house.evaluate()

    @property
    def measured_drop(self) -> float | None:
        """The drop of the last hours; None until there are enough samples."""
        return self._measured

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    @property
    def drop_from(self) -> str:
        """manual, measured, last (measured before a restart) or default (nothing measured yet)."""
        if self.drop_mode == "manual":
            return "manual"
        if self.measured_drop is not None:
            return "measured"
        return "last" if "drop" in self._stored else "default"

    @property
    def drop(self) -> float:
        """°C the water at the mixers is below the setting: measured or by hand.

        Until enough is measured (after a restart), the last measured value holds.
        """
        if self.drop_mode == "manual":
            return self.manual_drop
        if self._measured is not None:
            return self._measured
        return float(self._stored.get("drop", DEFAULT_TANK_DROP))

    @property
    def reserve(self) -> float:
        return float(tuned(self, "reserve"))

    @property
    def margin(self) -> float:
        """°C the setting is above the warmest circuit target: reserve + tank drop."""
        return self.reserve + self.drop

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
            margin=self.margin,
            minimum=max(lowest, low) if low is not None else lowest,
            maximum=min(highest, high) if high is not None else highest,
            step=step,
            threshold=max(1.0, step),
            interval=SETPOINT_INTERVAL,
        )

    @callback
    def evaluate_setpoint(self, mode: Mode) -> None:
        """After the circuits: measure the tank drop, set the source; then its entities."""
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
        self._measure_drop(current, heating)
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
        """From the entity chosen for it, else the heat pump's supply far above the tank."""
        s = self.settings
        if s.hot_water_entity:
            state = state_of(self.house.hass, s.hot_water_entity)
            return state.state == "on" if state else None
        supply, tank = float_of(self.house.hass, s.heater_supply), self.temperature()
        if supply is None or tank is None:
            return None
        return supply - tank >= tuned(self, "hot_water_gap")

    def _defrosts(self) -> bool | None:
        """The heat pump reverses to defrost: its supply comes back colder than its return."""
        hass, s = self.house.hass, self.settings
        supply, back = float_of(hass, s.heater_supply), float_of(hass, s.heater_return)
        if supply is None or back is None:
            return None
        return supply < back - DEFROST_GAP

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
            if not now:
                self._busy_ended = self.house.now()
            self._log_event(f"{key}_on" if now else f"{key}_off")

    def _heat_generator_busy(self) -> bool:
        """Heating hot water or defrosting, or the tank still recovering from it."""
        if self.hot_water_heating or self.defrosting:
            return True
        ended = self._busy_ended
        return ended is not None and self.house.now() - ended < HEAT_GENERATOR_RECOVERY

    def _measure_drop(self, setting: float | None, heating: list[Circuit]) -> None:
        """A sample a minute while a circuit heats: the setting minus the water at the mixers.

        Not while the heat generator is busy elsewhere or the tank recovers from it, and not
        until the setting has stood for a while: the tank still heats up or cools down then,
        and counting it would push the setting further on its own.
        """
        now = self.house.now()
        if setting is not None and setting != self._setting:  # not when it drops out a moment
            self._setting, self._setting_since = setting, now
        window = 3600 * tuned(self, "drop_window")
        if self._samples and now - self._samples[0][0] > window:
            while self._samples and now - self._samples[0][0] > window:
                self._samples.popleft()
            self._measured = tank_drop([value for _, value in self._samples])
        if (
            setting is None
            or not heating
            or self._heat_generator_busy()
            or now - (self._setting_since or now) < DROP_SETTLE
            or (self._sampled_at is not None and now - self._sampled_at < DROP_SAMPLE_INTERVAL - 1)
            or (water := self._water_at_mixers(heating)) is None
        ):
            return
        self._samples.append((now, setting - water))
        self._sampled_at = now
        self._measured = measured = tank_drop([value for _, value in self._samples])
        if measured is not None and abs(measured - self._stored.get("drop", -99.0)) >= 0.5:
            self._stored["drop"] = measured  # holds until enough is measured after a restart
            self.house.save()

    def _water_at_mixers(self, heating: list[Circuit]) -> float | None:
        """The tank's outlet, or the supply of a mixer fully open (the same water), the lower."""
        values = [self.temperature()]
        for circuit in heating:
            mixer = circuit.mixer
            if mixer is not None and (mixer.position() or 0) >= FULLY_OPEN:
                values.append(circuit.supply_temperature())
        known = [v for v in values if v is not None]
        return min(known) if known else None

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
            self.drop,
            self.drop_from,
            tuned(self, "drop_window"),
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
        """Before the circuits: is the heat generator busy with hot water or a defrost."""
        self._watch_heat_generator()
