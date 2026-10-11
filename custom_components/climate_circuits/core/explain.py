"""Why a circuit heats, cools or stays idle, zone by zone; texts.py makes sentences of it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .demand import ACTIVE_ACTIONS, Demand
from .mode import Mode


class ZoneStatus(StrEnum):
    CALLING = "calling"
    SATISFIED = "satisfied"
    WAITING = "waiting"  # below target, within the thermostat's tolerance
    OFF = "off"
    UNAVAILABLE = "unavailable"


class CircuitState(StrEnum):
    HEATING = "heating"
    COOLING = "cooling"
    IDLE = "idle"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class ZoneSnapshot:
    entity_id: str
    name: str
    available: bool
    hvac_mode: str | None = None
    hvac_action: str | None = None
    current: float | None = None
    target: float | None = None


@dataclass(frozen=True, slots=True)
class ZoneExplanation:
    zone: ZoneSnapshot
    status: ZoneStatus


@dataclass(frozen=True, slots=True)
class CircuitExplanation:
    state: CircuitState
    mode: Mode
    zones: tuple[ZoneExplanation, ...]
    has_zones: bool

    def count(self, status: ZoneStatus) -> int:
        return sum(1 for z in self.zones if z.status is status)

    @property
    def calling(self) -> tuple[ZoneExplanation, ...]:
        return tuple(z for z in self.zones if z.status is ZoneStatus.CALLING)


def zone_status(mode: Mode, zone: ZoneSnapshot) -> ZoneStatus:
    if not zone.available:
        return ZoneStatus.UNAVAILABLE
    if zone.hvac_mode == "off" or zone.hvac_action == "off":
        return ZoneStatus.OFF
    if mode is not Mode.OFF and zone.hvac_action in ACTIVE_ACTIONS[mode]:
        return ZoneStatus.CALLING
    if zone.current is None or zone.target is None:
        return ZoneStatus.SATISFIED
    reached = zone.current <= zone.target if mode is Mode.COOL else zone.current >= zone.target
    return ZoneStatus.SATISFIED if reached else ZoneStatus.WAITING


def explain_circuit(
    mode: Mode, zones: Sequence[ZoneSnapshot], demand: Demand
) -> CircuitExplanation:
    if mode is Mode.OFF:
        state = CircuitState.OFF
    elif demand.active:
        state = CircuitState.HEATING if mode is Mode.HEAT else CircuitState.COOLING
    else:
        state = CircuitState.IDLE
    explained = tuple(ZoneExplanation(z, zone_status(mode, z)) for z in zones)
    return CircuitExplanation(state, mode, explained, has_zones=bool(zones))
