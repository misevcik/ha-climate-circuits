"""Three-point mixing valve without feedback: position estimated from relay run times.

The supply temperature answers a move only after the water reaches the sensor (one to three
minutes), so after a move the regulation waits, and it does not move while the temperature
is already heading for the target. Without that it overshoots and swings.

At an end stop the relay is pulsed now and then so the valve really sits there.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class Direction(StrEnum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class MixerSettings:
    travel: float = 125.0  # s, full stroke
    hysteresis: float = 0.5  # K
    settle: float = 150.0  # s after a move before the next one, the water reaches the sensor
    end_pulse: float = 2.0  # s
    end_pulse_interval: float = 600.0  # s, at an end stop while regulating
    idle_pulse_interval: float = 21600.0  # s, closed without demand
    gain: float = 4.0  # % of travel per K of difference
    min_step: int = 2  # %
    max_step: int = 20  # %
    trend_window: float = 120.0  # s of supply readings the trend is taken from


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
    """A small step near the target, a larger one far from it."""
    return min(max(round(abs(diff) * settings.gain), settings.min_step), settings.max_step)


def supply_trend(samples: Sequence[tuple[float, float]], now: float, window: float) -> float | None:
    """K per minute over the last window; None until the readings cover half of it."""
    recent = [(t, v) for t, v in samples if now - t <= window]
    if len(recent) < 2 or recent[-1][0] - recent[0][0] < window / 2:
        return None
    (t0, v0), (t1, v1) = recent[0], recent[-1]
    return (v1 - v0) / (t1 - t0) * 60.0


def homing_action(settings: MixerSettings, reason: str) -> MixerAction:
    return MixerAction(
        Direction.CLOSE, settings.travel + settings.end_pulse, reason, end_pulse=True, homing=True
    )


def _end_pulse(
    direction: Direction,
    since_pulse: float | None,
    interval: float,
    settings: MixerSettings,
    reason: str,
) -> MixerAction | None:
    if since_pulse is not None and since_pulse < interval:
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
    since_move: float | None = None,
    trend: float | None = None,
) -> MixerAction | None:
    """One step, or None to stay. Opening means "more" in both modes.

    since_move: s since the last move ended; trend: supply change in K per minute.
    """
    if position is None:
        return homing_action(settings, "position unknown")
    if not demand:
        if position > 0:
            seconds = position / 100.0 * settings.travel + settings.end_pulse
            return MixerAction(Direction.CLOSE, seconds, "no demand, closing", end_pulse=True)
        return _end_pulse(
            Direction.CLOSE,
            since_end_pulse,
            settings.idle_pulse_interval,
            settings,
            "no demand, closed",
        )
    if target is None or supply is None or abs(target - supply) <= settings.hysteresis:
        return None
    if since_move is not None and since_move < settings.settle:
        return None  # the last move has not reached the sensor yet
    if trend is not None:
        expected = supply + trend * settings.settle / 60.0
        if (target - supply) * (target - expected) <= 0:
            return None  # already on its way: it gets there before the next move could help

    more = supply < target if heating else supply > target
    direction = Direction.OPEN if more else Direction.CLOSE
    room = 100.0 - position if more else position
    if room <= 0:
        return _end_pulse(
            direction,
            since_end_pulse,
            settings.end_pulse_interval,
            settings,
            f"at end stop, {direction}",
        )
    step = min(float(step_size(target - supply, settings)), room)
    seconds = step / 100.0 * settings.travel
    reason = f"{direction} {step:.0f} % (target {target:.1f}, supply {supply:.1f})"
    if step == room:
        return MixerAction(direction, seconds + settings.end_pulse, reason, end_pulse=True)
    return MixerAction(direction, seconds, reason)
