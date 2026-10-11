"""Demand of a circuit from the thermostats of its zones."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .mode import Mode

ACTIVE_ACTIONS = {
    Mode.HEAT: frozenset({"heating", "preheating"}),
    Mode.COOL: frozenset({"cooling"}),
}


@dataclass(frozen=True, slots=True)
class Demand:
    active: bool
    zones: tuple[str, ...] = ()
    reason: str = ""


def circuit_demand(
    mode: Mode,
    heating_zones: Sequence[str],
    cooling_zones: Sequence[str],
    hvac_actions: Mapping[str, str | None],
) -> Demand:
    """On when a zone of the mode heats or cools; a circuit without zones runs with the mode."""
    if mode is Mode.OFF:
        return Demand(False, reason="mode off")
    zones = heating_zones if mode is Mode.HEAT else cooling_zones
    if not zones:
        return Demand(True, reason=f"no {mode} zones, runs with the mode")
    if active := tuple(z for z in zones if hvac_actions.get(z) in ACTIVE_ACTIONS[mode]):
        return Demand(True, active, f"{len(active)} of {len(zones)} zones call")
    return Demand(False, reason=f"none of {len(zones)} zones call")
