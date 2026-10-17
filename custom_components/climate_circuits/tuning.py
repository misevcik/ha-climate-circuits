"""Thresholds and constants that are set on the devices, as entities, not in the forms.

The forms only choose which entities are connected. Each value here is a number or switch on
the device it belongs to (house, circuit, heat source, hot water). Until it is changed there,
it is what the older configuration held, or the default; a change is stored with the rest of
the runtime state and applies at once, without a reload.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN


@dataclass(frozen=True, slots=True)
class Tunable:
    key: str  # the entity's translation key and the stored key
    minimum: float
    maximum: float
    step: float
    unit: str | None
    default: Callable[[Any], Any]  # from the owner's settings: older configuration or default


@dataclass(frozen=True, slots=True)
class TunableSwitch:
    key: str
    default: Callable[[Any], bool]


MIXER = (
    Tunable("travel", 10, 600, 1, "s", lambda c: c.settings.mixer.travel),
    Tunable("hysteresis", 0.1, 5, 0.1, "°C", lambda c: c.settings.mixer.hysteresis),
    Tunable("settle", 30, 600, 10, "s", lambda c: c.settings.mixer.settle),
    Tunable("gain", 0.5, 20, 0.5, "%/°C", lambda c: c.settings.mixer.gain),
    Tunable("min_step", 1, 20, 1, "%", lambda c: c.settings.mixer.min_step),
    Tunable("max_step", 1, 100, 1, "%", lambda c: c.settings.mixer.max_step),
    Tunable("trend_window", 30, 600, 10, "s", lambda c: c.settings.mixer.trend_window),
    Tunable("min_source_gap", 1, 20, 0.5, "°C", lambda c: c.settings.mixer.min_source_gap),
)
MIXER_SWITCHES = (TunableSwitch("source_compensation", lambda c: c.settings.mixer.compensate),)
PUMP = (
    Tunable("pump_delay", 0, 900, 10, "s", lambda c: c.settings.pump_delay),
    Tunable("pump_run_on", 0, 900, 10, "s", lambda c: c.settings.pump_run_on),
)
SOURCE = (
    Tunable("setpoint_min", 10, 80, 1, "°C", lambda s: s.settings.setpoint_min),
    Tunable("setpoint_max", 10, 80, 1, "°C", lambda s: s.settings.setpoint_max),
    Tunable("manual_pause", 0, 1440, 1, "min", lambda s: s.settings.manual_pause),
)
HOT_WATER = (
    Tunable("circulation_threshold", 20, 60, 0.5, "°C", lambda h: h.settings.threshold),
    Tunable("circulation_delta", 0.5, 10, 0.5, "°C", lambda h: h.settings.delta),
)
HOUSE = (
    Tunable("mode_pause", 0, 240, 5, "min", lambda h: h.settings.mode_pause / 60),
    Tunable("exercise_days", 0, 60, 1, "d", lambda h: h.settings.exercise_days),
)
FALLBACK = (
    Tunable("heat_threshold", -30, 90, 0.5, "°C", lambda h: h.settings.mode.heat_threshold),
    Tunable("cool_threshold", -30, 90, 0.5, "°C", lambda h: h.settings.mode.cool_threshold),
)
HOUSE_SWITCHES = (TunableSwitch("home_mixers_on_start", lambda h: h.settings.home_mixers_on_start),)

_ALL = {t.key: t for t in (*MIXER, *MIXER_SWITCHES, *PUMP, *SOURCE, *HOT_WATER, *HOUSE)}
_ALL |= {t.key: t for t in (*FALLBACK, *HOUSE_SWITCHES)}
# Pairs that must keep their order: (lower, upper).
_ORDERED = (("min_step", "max_step"), ("setpoint_min", "setpoint_max"))


def tuned(owner: Any, key: str) -> Any:
    """The value set on the device, else the one from the configuration or the default.

    owner: anything with .house, .id and .settings (the house, a circuit, a source, hot water).
    """
    stored = owner.house.persisted["tuning"].get(owner.id, {})
    return stored[key] if key in stored else _ALL[key].default(owner)


def set_tuned(owner: Any, key: str, value: Any) -> None:
    """Store a value set on the device and apply it at once."""
    for lower, upper in _ORDERED:
        if key == lower and value > tuned(owner, upper):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="above_max")
        if key == upper and value < tuned(owner, lower):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="below_min")
    house = owner.house
    house.persisted["tuning"].setdefault(owner.id, {})[key] = value
    house.save()
    house.retune()
    house.evaluate()


def tunables(house: Any) -> list[tuple[Any, tuple[Tunable | TunableSwitch, ...]]]:
    """Each owner (house, circuit, source, hot water) with the values set on its device."""
    owners: list[tuple[Any, tuple[Tunable | TunableSwitch, ...]]] = [
        (house, (*HOUSE, *HOUSE_SWITCHES, *(FALLBACK if house.settings.fallback_sensor else ())))
    ]
    for circuit in house.circuits.values():
        values = (
            *(PUMP if circuit.pump else ()),
            *(MIXER + MIXER_SWITCHES if circuit.mixer else ()),
        )
        if values:
            owners.append((circuit, values))
    owners += [(source, SOURCE) for source in house.sources.values() if source.controllable]
    if house.hot_water:
        owners.append((house.hot_water, HOT_WATER))
    return owners


def seed(house: Any) -> None:
    """Keep what the forms held before these values moved to the devices."""
    for owner, values in tunables(house):
        stored = house.persisted["tuning"].setdefault(owner.id, {})
        for tunable in values:
            if tunable.key not in stored and (value := tunable.default(owner)) is not None:
                stored[tunable.key] = value
