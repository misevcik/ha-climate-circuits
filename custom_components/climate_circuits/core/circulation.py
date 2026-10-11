"""Hot water circulation pump: hysteresis on the circulation return temperature."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CirculationReason(StrEnum):
    COLD = "cold"  # below threshold − delta: start
    WARMING = "warming"  # running, below threshold: keep running
    REACHED = "reached"  # at threshold: stop
    WAITING = "waiting"  # stopped inside the band
    DISABLED = "disabled"
    NO_SENSOR = "no_sensor"


@dataclass(frozen=True, slots=True)
class CirculationDecision:
    on: bool
    reason: CirculationReason
    temperature: float | None
    on_below: float
    off_at: float


def circulation_decision(
    temperature: float | None, threshold: float, delta: float, running: bool, enabled: bool
) -> CirculationDecision:
    if not enabled:
        on, reason = False, CirculationReason.DISABLED
    elif temperature is None:
        on, reason = False, CirculationReason.NO_SENSOR
    elif temperature >= threshold:
        on, reason = False, CirculationReason.REACHED
    elif temperature < threshold - delta:
        on, reason = True, CirculationReason.COLD
    elif running:
        on, reason = True, CirculationReason.WARMING
    else:
        on, reason = False, CirculationReason.WAITING
    return CirculationDecision(on, reason, temperature, threshold - delta, threshold)
