"""House mode: heat, cool or off, from an ordered list of sources."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    HEAT = "heat"
    COOL = "cool"
    OFF = "off"


class Override(StrEnum):
    AUTO = "auto"
    HEAT = "heat"
    COOL = "cool"
    OFF = "off"


class FallbackKind(StrEnum):
    NONE = "none"
    TANK = "tank"  # warm water means heating, cold water cooling
    OUTDOOR = "outdoor"  # cold outside means heating, hot outside cooling


class ModeSource(StrEnum):
    OVERRIDE = "override"
    ENTITY = "entity"
    FALLBACK = "fallback"
    LAST = "last"
    DEFAULT = "default"


@dataclass(frozen=True, slots=True)
class ModeSettings:
    """Tank: heat ≥ heat_threshold, cool ≤ cool_threshold. Outdoor: the other way round."""

    capabilities: frozenset[Mode]
    fallback: FallbackKind = FallbackKind.NONE
    heat_threshold: float | None = None
    cool_threshold: float | None = None


@dataclass(frozen=True, slots=True)
class ModeDecision:
    mode: Mode
    source: ModeSource
    reason: str


@dataclass(frozen=True, slots=True)
class EntityMapping:
    """Values of a select/sensor source that mean each mode."""

    heat: Collection[str] = ()
    cool: Collection[str] = ()
    off: Collection[str] = ()


CLIMATE_MODES = {"heat": Mode.HEAT, "cool": Mode.COOL, "off": Mode.OFF}
ON_OFF_DOMAINS = frozenset({"binary_sensor", "switch", "input_boolean"})


def mode_from_entity(domain: str, state: str | None, mapping: EntityMapping) -> Mode | None:
    if state is None:
        return None
    if domain == "climate":
        return CLIMATE_MODES.get(state)
    if domain in ON_OFF_DOMAINS:
        return {"on": Mode.HEAT, "off": Mode.OFF}.get(state)
    for mode in Mode:
        if state in getattr(mapping, mode.value):
            return mode
    return None


def _fallback_mode(settings: ModeSettings, temperature: float, last: Mode | None) -> Mode | None:
    heat, cool = settings.heat_threshold, settings.cool_threshold
    if settings.fallback is FallbackKind.TANK:
        if heat is not None and temperature >= heat:
            return Mode.HEAT
        if cool is not None and temperature <= cool:
            return Mode.COOL
        return last  # between thresholds: hysteresis
    if heat is not None and temperature <= heat:
        return Mode.HEAT
    if cool is not None and temperature >= cool:
        return Mode.COOL
    return Mode.OFF


def resolve_mode(
    settings: ModeSettings,
    override: Override,
    entity_mode: Mode | None,
    fallback_temperature: float | None,
    last: Mode | None,
) -> ModeDecision:
    """Override, source entity, fallback temperature, last mode. Unsupported modes become off."""

    def capable(mode: Mode) -> bool:
        return mode is Mode.OFF or mode in settings.capabilities

    if override is not Override.AUTO:
        mode = Mode(override.value)
        if not capable(mode):
            return ModeDecision(Mode.OFF, ModeSource.OVERRIDE, f"override {mode} not supported")
        return ModeDecision(mode, ModeSource.OVERRIDE, f"override {mode}")
    if entity_mode is not None:
        if not capable(entity_mode):
            return ModeDecision(Mode.OFF, ModeSource.ENTITY, f"source {entity_mode} not supported")
        return ModeDecision(entity_mode, ModeSource.ENTITY, f"source entity {entity_mode}")
    if settings.fallback is not FallbackKind.NONE and fallback_temperature is not None:
        mode = _fallback_mode(settings, fallback_temperature, last)
        if mode is not None:
            mode = mode if capable(mode) else Mode.OFF
            return ModeDecision(
                mode, ModeSource.FALLBACK, f"fallback {fallback_temperature:.1f} °C → {mode}"
            )
    if last is not None:
        return ModeDecision(last, ModeSource.LAST, f"keeping last mode {last}")
    return ModeDecision(Mode.OFF, ModeSource.DEFAULT, "no source available")
