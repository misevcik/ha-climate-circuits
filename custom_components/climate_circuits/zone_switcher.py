"""Switching the zone thermostats when the house changes between heating and cooling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import callback

from .const import ZONE_COMMAND_ATTEMPTS, ZONE_COMMAND_RETRY
from .core.mode import Mode, ModeDecision, ModeSource
from .core.texts import other_zones_kind, zones_message
from .core.zones import OFF, ZonePlan, plan_zones
from .states import call_service, name_of, state_of

if TYPE_CHECKING:
    from .house import House


class ZoneSwitcher:
    """Switches thermostat sets on a mode change and keeps the other set off.

    The other mode's thermostats are turned off first; the new ones are switched on only
    once all of those report off (both sets drive the same zone relays). A thermostat of
    the other mode that comes on later (a schedule, a person) is turned off again.
    """

    def __init__(self, house: House) -> None:
        self.house = house
        self.mode: Mode | None = None  # mode the thermostats were last switched for
        self.switching: Mode | None = None  # new mode waiting for its thermostats
        self.plan: ZonePlan | None = None
        self._sent: dict[str, tuple[str, float, int]] = {}  # zone: (hvac mode, time, attempts)
        self._failed: set[str] = set()
        self._stray: set[str] = set()
        self._unavailable: tuple[str, ...] = ()

    def _name(self, entity_id: str) -> str:
        return name_of(self.house.hass, entity_id) or entity_id

    def _names(self, zones: Any) -> list[str]:
        return [self._name(z) for z in zones]

    def _log(self, key: str, mode: Mode, **values: Any) -> None:
        house = self.house
        message = zones_message(
            key, mode, house.hass.config.language, not house.control_equipment, **values
        )
        house.activity("Climate Circuits", message, f"{house.entry.entry_id}_mode")

    @callback
    def evaluate(self, decision: ModeDecision) -> None:
        house = self.house
        if not house.settings.switch_zones:
            self.plan = None
            return
        # Before async_start nothing is logged yet; without a source the mode is a guess.
        if not house.logging or decision.source is ModeSource.DEFAULT:
            return
        mode = decision.mode
        heating = [z for c in house.circuits.values() for z in c.settings.heating_zones]
        cooling = [z for c in house.circuits.values() for z in c.settings.cooling_zones]
        hvac_modes = {
            z: state.state if (state := state_of(house.hass, z)) else None
            for z in {*heating, *cooling}
        }
        changed = self.mode is not None and mode is not self.mode
        if changed:
            self.switching = mode if mode is not Mode.OFF else None
            self._sent.clear()
            self._failed.clear()
        self.mode = mode
        plan = self.plan = plan_zones(mode, heating, cooling, hvac_modes, self.switching is mode)
        off, on = self._names(plan.turn_off), self._names(plan.turn_on)

        if changed:
            if off and on:
                self._log("switch", mode, off=off, on=on)
            elif off or on:
                self._log("switch_off" if off else "turn_on", mode, off=off, on=on)
            else:
                self._log("nothing", mode)
        elif stray := [z for z in plan.turn_off if z not in self._stray]:
            self._log("stray", mode, names=", ".join(self._names(stray)))
        self._stray = set(plan.turn_off)
        if plan.unavailable and plan.unavailable != self._unavailable:
            self._log("unavailable", mode, names=", ".join(self._names(plan.unavailable)))
        self._unavailable = plan.unavailable

        if not house.control_equipment:
            self.switching = None  # dry run: nothing waits for thermostats
            return
        for zone in plan.turn_off:
            self._command(zone, OFF, mode)
        if self.switching is mode and not plan.blocked:
            if on and not changed:
                self._log("turn_on", mode, on=on)
            for zone in plan.turn_on:
                self._command(zone, plan.hvac_mode or OFF, mode)
            self.switching = None
        for zone in [z for z, (m, _, _) in self._sent.items() if hvac_modes.get(z) == m]:
            del self._sent[zone]

    @callback
    def _command(self, zone: str, hvac_mode: str, mode: Mode) -> None:
        """Repeated at most every ZONE_COMMAND_RETRY s, reported after the last attempt."""
        hass = self.house.hass
        now = hass.loop.time()
        sent = self._sent.get(zone)
        attempts = sent[2] if sent and sent[0] == hvac_mode else 0
        if sent and attempts and now - sent[1] < ZONE_COMMAND_RETRY:
            return
        if attempts >= ZONE_COMMAND_ATTEMPTS:
            if zone not in self._failed:
                self._failed.add(zone)
                self._log("failed", mode, names=self._name(zone), n=attempts)
            return
        self._sent[zone] = (hvac_mode, now, attempts + 1)
        call_service(hass, "climate", "set_hvac_mode", entity_id=zone, hvac_mode=hvac_mode)

    def details(self) -> dict[str, Any]:
        if (plan := self.plan) is None:
            return {}
        return {
            "zones_must_be_off": other_zones_kind(
                self.mode or Mode.OFF, self.house.hass.config.language
            ),
            "zones_still_on": self._names(plan.turn_off),
            "zones_waiting_to_turn_on": self._names(plan.turn_on) if self.switching else [],
            "zones_failed": self._names(sorted(self._failed)),
        }
