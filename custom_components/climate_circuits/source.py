"""A heat source (buffer tank, boiler, heat pump): the water it gives the circuits, and
optionally its setting from the circuits.

Setting it from the circuits (its own switch, and Control equipment on): the warmest water a
heating circuit wants plus a margin. The margin learns from the mixers: up when a mixer is
fully open and still short, down when all of them have been well below fully open for an
hour. It can also be set by hand. A change of the setting by somebody else (the heat pump's
app) pauses this for a few hours.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import callback

from .const import (
    COMFORTABLE_OPENING,
    CONTROLLABLE_SETPOINTS,
    HOT_WATER_RECOVERY,
    SETPOINT_INTERVAL,
)
from .core.mode import Mode
from .core.setpoint import (
    MarginSettings,
    SetpointDecision,
    SetpointSettings,
    next_margin,
    setpoint_decision,
)
from .core.texts import setpoint_event_text, setpoint_text
from .listeners import Listeners
from .settings import SourceSettings
from .states import call_service, float_of, number, state_of
from .tuning import tuned

if TYPE_CHECKING:
    from .circuit import Circuit
    from .house import House

MARGIN = MarginSettings()
MARGIN_MODES = ("auto", "manual")  # learned from the mixers, or the value set by hand


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
        self._margin_changed_at: float | None = None
        self._comfortable_since: float | None = None  # all heating mixers well below open
        self._was_paused = False
        self.hot_water_heating: bool | None = None  # None: cannot tell
        self._hot_water_ended: float | None = None

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
    def margin(self) -> float:
        """°C above the warmest circuit target: learned, or set by hand."""
        return float(self._stored.get("margin", self.settings.setpoint_margin))

    @property
    def margin_mode(self) -> str:
        return str(self._stored.get("margin_mode", "auto"))

    @callback
    def set_margin_mode(self, mode: str) -> None:
        """Back to auto, learning starts from the margin as it is."""
        self._stored["margin_mode"] = mode
        self._margin_changed_at = self.house.now()
        self._comfortable_since = None
        self.house.save()
        self.house.evaluate()

    @callback
    def set_margin(self, margin: float) -> None:
        """By hand: holds in manual mode; in auto mode learning goes on from here."""
        self._stored["margin"] = margin
        self._margin_changed_at = self.house.now()
        self._comfortable_since = None
        self.house.save()
        self.house.evaluate()

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
        """Set the source from the warmest water its heating circuits want (when switched on)."""
        if not self.controllable:
            return
        house = self.house
        current = self.setpoint()
        live = self.control_enabled and house.control_equipment
        self._watch_change_by_hand(current, live)
        paused = self.paused_until is not None
        self._log_resume(paused)
        heating = self._heating_circuits() if mode is Mode.HEAT else []
        if live and not paused and self.margin_mode == "auto":
            self._learn_margin(heating)
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

    def _watch_hot_water(self) -> None:
        """Activity when the heat generator starts and stops heating hot water."""
        heating = self._heats_hot_water()
        was, self.hot_water_heating = self.hot_water_heating, heating
        if heating is None or was is None or heating == was:
            return
        if not heating:
            self._hot_water_ended = self.house.now()
        self._log_event("hot_water_on" if heating else "hot_water_off")

    def _recovering_from_hot_water(self) -> bool:
        """Heating hot water, or the tank still recovering from it: water short for that."""
        if self.hot_water_heating:
            return True
        ended = self._hot_water_ended
        return ended is not None and self.house.now() - ended < HOT_WATER_RECOVERY

    def _learn_margin(self, heating: list[Circuit]) -> None:
        """Up when a mixer is short of water, down after an hour of water warmer than needed.

        Not up while the heat generator heats hot water or the tank recovers from it: the
        water is short for that, not for a setting too low.
        """
        mixers = [c for c in heating if c.mixer is not None]
        if not mixers:
            self._comfortable_since = None
            return
        now = self.house.now()
        starved = [c.name for c in mixers if c.mixer.starved]
        if self._recovering_from_hot_water():
            starved = []
        if all(self._comfortable(c) for c in mixers):
            self._comfortable_since = self._comfortable_since or now
        else:
            self._comfortable_since = None
        margin, why = next_margin(
            self.margin,
            starved=bool(starved),
            comfortable_for=None
            if self._comfortable_since is None
            else now - self._comfortable_since,
            since_change=None if self._margin_changed_at is None else now - self._margin_changed_at,
            settings=MARGIN,
        )
        if why is None:
            return
        self._stored["margin"] = margin
        self._margin_changed_at = now
        self._comfortable_since = None  # another hour before the next lowering
        self.house.save()
        self._log_event(f"margin_{why}", margin=margin, circuit=", ".join(starved))

    @staticmethod
    def _comfortable(circuit: Circuit) -> bool:
        """Well below fully open and at its target: the water is warmer than it needs."""
        mixer, target = circuit.mixer, circuit.target
        position, supply = mixer.position(), circuit.supply_temperature()
        if position is None or supply is None or target is None:
            return False
        return position <= COMFORTABLE_OPENING and supply >= target.value - mixer.params.hysteresis

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
            self.margin,
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
                [s.temperature_sensor, s.setpoint_entity, s.heater_supply, s.hot_water_entity],
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
        self._watch_hot_water()
        self._notify()
