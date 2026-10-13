"""Typed views of the house options and the circuit and source subentries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
    DEFAULT_COOL_CURVE,
    DEFAULT_DELTA,
    DEFAULT_EXERCISE_DAYS,
    DEFAULT_GAIN,
    DEFAULT_HEAT_CURVE,
    DEFAULT_HYSTERESIS,
    DEFAULT_MAX_STEP,
    DEFAULT_MIN_SOURCE_GAP,
    DEFAULT_MIN_STEP,
    DEFAULT_MODE_PAUSE,
    DEFAULT_PUMP_DELAY,
    DEFAULT_PUMP_RUN_ON,
    DEFAULT_SETTLE,
    DEFAULT_THRESHOLD,
    DEFAULT_TRAVEL,
    DEFAULT_TREND_WINDOW,
)
from .core.curve import Curve
from .core.mixer import MixerSettings
from .core.mode import EntityMapping, FallbackKind, Mode, ModeSettings


@dataclass(frozen=True, slots=True)
class HotWaterSettings:
    sensor: str
    pump: str
    threshold: float
    delta: float

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> HotWaterSettings | None:
        """None when the circulation sensor or pump is not set."""
        hw = options.get("hot_water", {})
        if not hw.get("circulation_sensor") or not hw.get("circulation_pump"):
            return None
        return cls(
            hw["circulation_sensor"],
            hw["circulation_pump"],
            float(hw.get("threshold", DEFAULT_THRESHOLD)),
            float(hw.get("delta", DEFAULT_DELTA)),
        )


@dataclass(frozen=True, slots=True)
class HouseSettings:
    mode: ModeSettings
    mode_entity: str | None
    mapping: EntityMapping
    fallback_sensor: str | None
    outdoor_sensor: str | None
    info_sensors: tuple[str, ...] = ()
    hot_water: HotWaterSettings | None = None
    switch_zones: bool = True
    mode_pause: float = DEFAULT_MODE_PAUSE * 60  # s
    exercise_days: float = DEFAULT_EXERCISE_DAYS
    home_mixers_on_start: bool = False

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> HouseSettings:
        mode, fallback = options.get("mode", {}), options.get("fallback", {})
        zone_control, protection = options.get("zone_control", {}), options.get("protection", {})
        return cls(
            mode=ModeSettings(
                capabilities=frozenset(Mode(c) for c in mode.get("capabilities", ["heat"])),
                fallback=FallbackKind(fallback.get("kind", FallbackKind.NONE)),
                heat_threshold=fallback.get("heat_threshold"),
                cool_threshold=fallback.get("cool_threshold"),
            ),
            mode_entity=mode.get("mode_entity"),
            mapping=EntityMapping(
                tuple(mode.get("heat_values", ())),
                tuple(mode.get("cool_values", ())),
                tuple(mode.get("off_values", ())),
            ),
            fallback_sensor=fallback.get("sensor"),
            outdoor_sensor=options.get("weather", {}).get("outdoor_sensor"),
            info_sensors=tuple(options.get("display", {}).get("info_sensors", ())),
            hot_water=HotWaterSettings.from_options(options),
            switch_zones=bool(zone_control.get("switch_zones", True)),
            mode_pause=60.0 * float(protection.get("mode_pause", DEFAULT_MODE_PAUSE)),
            exercise_days=float(protection.get("exercise_days", DEFAULT_EXERCISE_DAYS)),
            home_mixers_on_start=bool(protection.get("home_mixers_on_start", False)),
        )


def _curve(values: Mapping[str, Any], defaults: Mapping[str, float]) -> Curve:
    """Unknown keys (an old heating slope) are ignored."""
    merged = {**defaults, **values}
    return Curve(**{key: float(merged[key]) for key in defaults})


@dataclass(frozen=True, slots=True)
class CircuitSettings:
    name: str
    heating_zones: tuple[str, ...]
    cooling_zones: tuple[str, ...]
    humidity_sensors: tuple[str, ...]
    heat_curve: Curve
    cool_curve: Curve
    pump: str | None
    mixer_open: str | None
    mixer_close: str | None
    supply_sensor: str | None
    mixer_position: str | None
    pump_delay: float
    pump_run_on: float
    mixer: MixerSettings = MixerSettings()
    source: str | None = None  # subentry id of the heat source it takes water from
    source_sensor: str | None = None  # 0.1.3, before heat sources existed

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> CircuitSettings:
        zones, outputs = data.get("zones", {}), data.get("outputs", {})
        return cls(
            name=data["name"],
            heating_zones=tuple(zones.get("heating_zones", ())),
            cooling_zones=tuple(zones.get("cooling_zones", ())),
            humidity_sensors=tuple(zones.get("humidity_sensors", ())),
            heat_curve=_curve(data.get("heat_curve", {}), DEFAULT_HEAT_CURVE),
            cool_curve=_curve(data.get("cool_curve", {}), DEFAULT_COOL_CURVE),
            pump=outputs.get("pump"),
            mixer_open=outputs.get("mixer_open"),
            mixer_close=outputs.get("mixer_close"),
            supply_sensor=outputs.get("supply_sensor"),
            mixer_position=outputs.get("mixer_position"),
            pump_delay=float(outputs.get("pump_delay", DEFAULT_PUMP_DELAY)),
            pump_run_on=float(outputs.get("pump_run_on", DEFAULT_PUMP_RUN_ON)),
            mixer=mixer_settings(data),
            source=outputs.get("source"),
            source_sensor=outputs.get("source_sensor"),
        )

    @property
    def zones(self) -> tuple[str, ...]:
        return self.heating_zones + self.cooling_zones


def mixer_section(data: Mapping[str, Any]) -> dict[str, Any]:
    """The mixer section; before 0.1.10 travel, hysteresis and settle were in the outputs."""
    outputs = data.get("outputs", {})
    old = {k: outputs[k] for k in ("travel", "hysteresis", "settle") if k in outputs}
    return old | dict(data.get("mixer", {}))


def mixer_settings(data: Mapping[str, Any]) -> MixerSettings:
    m = mixer_section(data)
    return MixerSettings(
        travel=float(m.get("travel", DEFAULT_TRAVEL)),
        hysteresis=float(m.get("hysteresis", DEFAULT_HYSTERESIS)),
        settle=float(m.get("settle", DEFAULT_SETTLE)),
        gain=float(m.get("gain", DEFAULT_GAIN)),
        min_step=int(m.get("min_step", DEFAULT_MIN_STEP)),
        max_step=int(m.get("max_step", DEFAULT_MAX_STEP)),
        trend_window=float(m.get("trend_window", DEFAULT_TREND_WINDOW)),
        compensate=bool(m.get("source_compensation", True)),
        min_source_gap=float(m.get("min_source_gap", DEFAULT_MIN_SOURCE_GAP)),
    )


@dataclass(frozen=True, slots=True)
class SourceSettings:
    """A buffer tank, boiler or heat pump the circuits take their water from."""

    name: str
    temperature_sensor: str | None
    setpoint_entity: str | None = None  # what the source is set to: a climate, number or sensor

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> SourceSettings:
        return cls(
            name=data["name"],
            temperature_sensor=data.get("temperature_sensor"),
            setpoint_entity=data.get("setpoint_entity"),
        )
