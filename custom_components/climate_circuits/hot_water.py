"""Hot water circulation: the pump keeps the circulation return between two temperatures.

It stops below the tank less a margin when the tank is cooler than the threshold allows, rests
for a pause after a run that took too long, and runs only within the schedule when one is set.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from .const import HOT_WATER_GRACE
from .core.circulation import (
    HELD_STATE,
    CirculationDecision,
    circulation_decision,
)
from .core.texts import circulation_message
from .listeners import Listeners
from .relay import Relay
from .settings import HotWaterSettings
from .states import float_of, state_of
from .tuning import tuned

if TYPE_CHECKING:
    from .house import House


class HotWater(Listeners):
    def __init__(self, house: House, settings: HotWaterSettings) -> None:
        super().__init__()
        self.house = house
        self.settings = settings
        self.enabled = True
        self.decision: CirculationDecision | None = None
        self._logged: tuple[Any, ...] | None = None
        self._running_since: float | None = None  # when the pump was first seen running
        self.paused_at: float | None = None  # wall clock, stored: a pause outlasts a reload
        self._controlled: bool | None = None  # control_equipment at the last evaluation
        self.relay = Relay(house, settings.pump, "Hot water circulation pump")

    @property
    def id(self) -> str:
        return f"{self.house.entry.entry_id}_hot_water"

    def linked_entities(self) -> dict[str, Any]:
        """What the circulation reads and switches, by role: shown on its device."""
        s = self.settings
        return {
            "circulation_sensor": s.sensor,
            "circulation_pump": s.pump,
            "tank_sensor": s.tank_sensor,
            "tank_setpoint": s.tank_setpoint,
            "circulation_schedule": s.schedule,
        }

    def inputs(self) -> set[str]:
        """The tank is read on the regular evaluation, not on each of its reports."""
        s = self.settings
        return {*filter(None, [s.sensor, s.pump, s.schedule])}

    def allowed(self) -> bool:
        """Within the schedule, or no schedule. A schedule that is not there does not stop it."""
        state = state_of(self.house.hass, self.settings.schedule)
        return state is None or state.state != "off"

    def pump_state(self) -> bool | None:
        return (
            state.state == "on"
            if (state := state_of(self.house.hass, self.settings.pump))
            else None
        )

    @property
    def paused_until(self) -> datetime | None:
        """When the current pause ends; follows a change of the pause length."""
        if self.paused_at is None or not (self.decision and self.decision.pause_left):
            return None
        return dt_util.utc_from_timestamp(self.paused_at + 60 * tuned(self, "circulation_pause"))

    def paused_until_text(self) -> str | None:
        """ "14:35", or "18.11. 10:00" when the pause ends on another day."""
        if (until := self.paused_until) is None:
            return None
        local = dt_util.as_local(until)
        today = dt_util.as_local(dt_util.utc_from_timestamp(self.house.wall())).date()
        time = f"{local:%H:%M}"
        return time if local.date() == today else f"{local.day}.{local.month}. {time}"

    @callback
    def evaluate(self) -> None:
        s = self.settings
        # The relay is the hysteresis memory, so a dry run mirrors a pump somebody else drives.
        pump = self.pump_state()
        running = pump if pump is not None else bool(self.decision and self.decision.on)
        house = self.house
        hass, wall = house.hass, house.wall()
        temperature = float_of(hass, s.sensor)
        if temperature is None and house.now() - house.started < HOT_WATER_GRACE:
            return  # sensors of boards that start with Home Assistant are not there yet
        before = self.paused_at
        if self.paused_at is not None and self.paused_at > wall:
            self.paused_at = wall  # stored under a clock that was ahead: at most a full pause
        if house.control_equipment != self._controlled:
            # A run counts from when the integration took (or left) control of the pump.
            self._controlled = house.control_equipment
            self._running_since = None
        pause, max_run = (
            60 * tuned(self, "circulation_pause"),
            60 * tuned(self, "circulation_max_run"),
        )
        if not (pause and max_run):
            self._running_since = None  # without the limit a run is not timed
        if self.paused_at is not None and wall - self.paused_at >= pause and running:
            # After a pause a run starts afresh, also when the pump never stopped (dry run).
            self._running_since = house.now()
        if pump is False or (pump is None and not running):
            self._running_since = None
        elif running and self._running_since is None:
            self._running_since = house.now()  # a relay not there yet does not end the run
        self.decision = circulation_decision(
            temperature,
            tuned(self, "circulation_threshold"),
            tuned(self, "circulation_delta"),
            running,
            self.enabled,
            tank=float_of(hass, s.tank_sensor),
            tank_margin=tuned(self, "circulation_tank_margin"),
            allowed=self.allowed(),
            ran_for=None if self._running_since is None else house.now() - self._running_since,
            paused_for=None if self.paused_at is None else max(0.0, wall - self.paused_at),
            max_run=max_run,
            pause=pause,
        )
        if self.decision.pause_started:
            self.paused_at = wall
        elif not self.decision.pause_left:
            self.paused_at = None
        if self.paused_at != before:
            house.save()
        self._log_change()
        if self.house.control_equipment and self.decision is not None:
            self.relay.ensure(self.decision.on)
        self._notify()

    @callback
    def _log_change(self) -> None:
        """Activity entry when the pump starts or stops, or cannot run."""
        decision, house = self.decision, self.house
        if not house.logging or decision is None:
            return
        special = decision.reason in HELD_STATE
        key = (decision.on, decision.reason if special else None)
        if key != self._logged:
            self._logged = key
            message = circulation_message(
                decision,
                house.hass.config.language,
                dry_run=not house.control_equipment,
                until=self.paused_until_text(),
            )
            house.activity("Hot water", message, f"{self.id}_circulation")

    @callback
    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.house.save()
        self.evaluate()
