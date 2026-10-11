"""Thermostat sets on a mode change.

Heating and cooling thermostats of a zone drive the same relay, so the other mode's
thermostats must report off before the new ones are switched on.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .mode import Mode

OFF = "off"


@dataclass(frozen=True, slots=True)
class ZonePlan:
    turn_off: tuple[str, ...]
    turn_on: tuple[str, ...]
    hvac_mode: str | None
    unavailable: tuple[str, ...]  # must be off, state unknown

    @property
    def blocked(self) -> bool:
        return bool(self.turn_off)


def plan_zones(
    mode: Mode,
    heating_zones: Iterable[str],
    cooling_zones: Iterable[str],
    hvac_modes: Mapping[str, str | None],
    switching: bool,
) -> ZonePlan:
    """hvac_modes: None = unavailable. switching: after a mode change, until switched on.

    A thermostat listed for both modes is never turned off, only switched.
    """
    heating, cooling = list(dict.fromkeys(heating_zones)), list(dict.fromkeys(cooling_zones))
    active = {Mode.HEAT: heating, Mode.COOL: cooling}.get(mode, [])
    other = [z for z in dict.fromkeys(heating + cooling) if z not in active]
    target = mode.value if mode is not Mode.OFF else None
    turn_on = [z for z in active if hvac_modes.get(z) not in (target, None)] if switching else []
    return ZonePlan(
        tuple(z for z in other if hvac_modes.get(z) not in (OFF, None)),
        tuple(turn_on) if target else (),
        target,
        tuple(z for z in other if hvac_modes.get(z) is None),
    )
