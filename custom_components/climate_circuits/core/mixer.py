"""Three-point mixing valve without feedback: position estimated from relay run times.

At an end stop the relay is pulsed now and then so the valve really sits there.
Not used yet; milestone 2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class Direction(StrEnum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class MixerSettings:
    travel: float = 125.0  # s, full stroke
    hysteresis: float = 0.5  # K
    end_pulse: float = 2.0  # s
    end_pulse_interval: float = 600.0  # s
    min_step: int = 5  # %
    max_step: int = 10  # %


@dataclass(frozen=True, slots=True)
class MixerAction:
    direction: Direction
    seconds: float
    reason: str
    end_pulse: bool = False
    homing: bool = False


def advance(position: float, direction: Direction, seconds: float, travel: float) -> float:
    delta = 100.0 * seconds / travel
    return min(max(position + (delta if direction is Direction.OPEN else -delta), 0.0), 100.0)


def step_size(diff: float, settings: MixerSettings) -> int:
    return min(settings.min_step + math.floor(abs(diff) + 0.5), settings.max_step)


def homing_action(settings: MixerSettings, reason: str) -> MixerAction:
    return MixerAction(
        Direction.CLOSE, settings.travel + settings.end_pulse, reason, end_pulse=True, homing=True
    )


def _end_pulse(
    direction: Direction, settings: MixerSettings, since_pulse: float | None, reason: str
) -> MixerAction | None:
    if since_pulse is not None and since_pulse < settings.end_pulse_interval:
        return None
    return MixerAction(direction, settings.end_pulse, reason, end_pulse=True)


def regulate(
    *,
    heating: bool,
    demand: bool,
    target: float | None,
    supply: float | None,
    position: float | None,
    since_end_pulse: float | None,
    settings: MixerSettings,
) -> MixerAction | None:
    """One step, or None to stay. Opening means "more" in both modes."""
    if position is None:
        return homing_action(settings, "position unknown")
    if not demand:
        if position > 0:
            seconds = position / 100.0 * settings.travel + settings.end_pulse
            return MixerAction(Direction.CLOSE, seconds, "no demand, closing", end_pulse=True)
        return _end_pulse(Direction.CLOSE, settings, since_end_pulse, "no demand, closed")
    if target is None or supply is None or abs(target - supply) <= settings.hysteresis:
        return None

    more = supply < target if heating else supply > target
    direction = Direction.OPEN if more else Direction.CLOSE
    room = 100.0 - position if more else position
    if room <= 0:
        return _end_pulse(direction, settings, since_end_pulse, f"at end stop, {direction}")
    step = min(float(step_size(target - supply, settings)), room)
    seconds = step / 100.0 * settings.travel
    reason = f"{direction} {step:.0f} % (target {target:.1f}, supply {supply:.1f})"
    if step == room:
        return MixerAction(direction, seconds + settings.end_pulse, reason, end_pulse=True)
    return MixerAction(direction, seconds, reason)
