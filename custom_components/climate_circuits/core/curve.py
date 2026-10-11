"""Target water temperature: weather curve plus the condensation floor."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .mode import Mode


@dataclass(frozen=True, slots=True)
class Curve:
    """Heating uses design point + exponent, cooling a straight line (slope)."""

    room: float
    minimum: float
    maximum: float
    correction: float = 0.0
    slope: float = 0.5
    design_outdoor: float = -15.0
    design_supply: float = 50.0
    exponent: float = 1.3


@dataclass(frozen=True, slots=True)
class WaterTarget:
    value: float
    reason: str


def raw_value(mode: Mode, curve: Curve, outdoor: float) -> float:
    """Curve value before limits.

    Heating: room + (design_supply − room) · φ^(1/n), φ = (room − out) / (room − design_out).
    Cooling: room − slope · (outdoor − room).
    """
    if mode is Mode.HEAT:
        load = max(curve.room - outdoor, 0.0) / max(curve.room - curve.design_outdoor, 1.0)
        raw = curve.room + (curve.design_supply - curve.room) * load ** (
            1.0 / max(curve.exponent, 0.5)
        )
    else:
        raw = curve.room - curve.slope * (outdoor - curve.room)
    return raw + curve.correction


def dew_point(temperature: float, humidity: float) -> float:
    """Magnus formula."""
    b, c = 17.62, 243.12
    gamma = math.log(min(max(humidity, 1.0), 100.0) / 100.0) + b * temperature / (c + temperature)
    return c * gamma / (b - gamma)


def worst_dew_point(temperatures: list[float], humidities: list[float]) -> float | None:
    """Sensors are not paired by room, so the warmest and most humid values are combined."""
    if not temperatures or not humidities:
        return None
    return dew_point(max(temperatures), max(humidities))


def water_target(
    mode: Mode, curve: Curve, outdoor: float | None, dew: float | None = None, margin: float = 2.0
) -> WaterTarget | None:
    """Curve clamped to [min, max]; cooling never below dew point + margin.

    Without an outdoor temperature the gentlest value is used (heating min, cooling max).
    """
    if mode is Mode.OFF:
        return None
    if outdoor is None:
        raw = curve.minimum if mode is Mode.HEAT else curve.maximum
        reason = "outdoor temperature unavailable"
    else:
        raw = raw_value(mode, curve, outdoor)
        reason = "curve"
    value = min(max(raw, curve.minimum), curve.maximum)
    if value != raw and outdoor is not None:
        reason = f"curve clamped to {'minimum' if value == curve.minimum else 'maximum'}"
    if mode is Mode.COOL and dew is not None and value < dew + margin:
        value = dew + margin
        reason = f"dew point {dew:.1f} °C + {margin:.1f} K"
    return WaterTarget(round(value, 1), reason)
