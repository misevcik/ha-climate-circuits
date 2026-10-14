"""Three-point mixing valve without feedback: position estimated from relay run times.

The supply temperature answers a move only after the water reaches the sensor (one to three
minutes), so after a move the regulation waits, and it does not move while the temperature
is already heading for the target. Without that it overshoots and swings.

With a source sensor (a buffer tank, a heat pump that cycles) a change of the source is met
at once: the supply is a mix of source and return water, so a source change of dT moves it
by about position x dT, and the valve is moved by the share that keeps the supply where it
is, without waiting for the supply sensor to see it.

At an end stop the relay is pulsed now and then so the valve really sits there.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class Direction(StrEnum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class MixerSettings:
    travel: float = 125.0  # s, full stroke
    hysteresis: float = 0.5  # °C
    settle: float = 150.0  # s after a move before the next one, the water reaches the sensor
    end_pulse: float = 2.0  # s
    end_pulse_interval: float = 600.0  # s, at an end stop while regulating
    idle_pulse_interval: float = 21600.0  # s, closed without demand
    gain: float = 4.0  # % of travel per °C of difference
    min_step: int = 2  # %
    max_step: int = 20  # %
    trend_window: float = 120.0  # s of supply readings the trend is taken from
    compensate: bool = True  # follow changes of the source at once
    min_source_gap: float = 3.0  # °C the source must be above the supply to compensate


@dataclass(frozen=True, slots=True)
class MixerAction:
    direction: Direction
    seconds: float
    reason: str
    end_pulse: bool = False
    homing: bool = False
    why: str = ""  # supply, source, no_demand, idle_pulse, end_stop, homing (for Activity)
    values: dict[str, float] = field(default_factory=dict)


def step_size(diff: float, settings: MixerSettings) -> int:
    """A small step near the target, a larger one far from it."""
    return min(max(round(abs(diff) * settings.gain), settings.min_step), settings.max_step)


def supply_trend(samples: Sequence[tuple[float, float]], now: float, window: float) -> float | None:
    """°C per minute over the last window; None until the readings cover half of it."""
    recent = [(t, v) for t, v in samples if now - t <= window]
    if len(recent) < 2 or recent[-1][0] - recent[0][0] < window / 2:
        return None
    (t0, v0), (t1, v1) = recent[0], recent[-1]
    return (v1 - v0) / (t1 - t0) * 60.0


def source_compensation(
    position: float, supply: float, source: float, source_ref: float, settings: MixerSettings
) -> float | None:
    """% to move (negative closes) so that the source change since source_ref leaves the supply.

    supply = return + (source - return) x p, so source - return = (source - supply) / (1 - p)
    and keeping the supply needs dp = -p x (1 - p) x dSource / (source - supply).
    """
    p = position / 100.0
    gap = source - supply
    if gap < settings.min_source_gap or not 0.0 < p < 1.0:
        return None
    return -100.0 * p * (1.0 - p) * (source - source_ref) / gap


def homing_action(settings: MixerSettings, reason: str) -> MixerAction:
    return MixerAction(
        Direction.CLOSE,
        settings.travel + settings.end_pulse,
        reason,
        end_pulse=True,
        homing=True,
        why="homing",
    )


def _end_pulse(
    direction: Direction,
    since_pulse: float | None,
    interval: float,
    settings: MixerSettings,
    reason: str,
    why: str,
    values: dict[str, float] | None = None,
) -> MixerAction | None:
    if since_pulse is not None and since_pulse < interval:
        return None
    return MixerAction(
        direction, settings.end_pulse, reason, end_pulse=True, why=why, values=values or {}
    )


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
    source: float | None = None,
    source_ref: float | None = None,
) -> MixerAction | None:
    """One step, or None to stay. Opening means "more" in both modes.

    since_move: s since the last move ended; trend: supply change in °C per minute;
    source: source temperature now, source_ref: what it was at the last move.
    """
    if position is None:
        return homing_action(settings, "position unknown")
    if not demand:
        if position > 0:
            seconds = position / 100.0 * settings.travel + settings.end_pulse
            return MixerAction(
                Direction.CLOSE,
                seconds,
                "no demand, closing",
                end_pulse=True,
                why="no_demand",
                values={"position": position},
            )
        return _end_pulse(
            Direction.CLOSE,
            since_end_pulse,
            settings.idle_pulse_interval,
            settings,
            "no demand, closed",
            "idle_pulse",
        )
    if settings.compensate and heating and None not in (supply, source, source_ref):
        change = source_compensation(position, supply, source, source_ref, settings)  # type: ignore[arg-type]
        if change is not None and abs(change) >= settings.min_step:
            direction = Direction.OPEN if change > 0 else Direction.CLOSE
            room = 100.0 - position if change > 0 else position
            step = min(abs(change), float(settings.max_step), room)
            if step >= settings.min_step:
                reason = f"{direction} {step:.0f} % (source {source_ref:.1f} -> {source:.1f})"
                return MixerAction(
                    direction,
                    step / 100.0 * settings.travel,
                    reason,
                    why="source",
                    values={"step": step, "ref": source_ref, "source": source, "supply": supply},
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
            "end_stop",
            {"supply": supply, "target": target, "position": position},
        )
    step = min(float(step_size(target - supply, settings)), room)
    seconds = step / 100.0 * settings.travel
    reason = f"{direction} {step:.0f} % (target {target:.1f}, supply {supply:.1f})"
    values = {"step": step, "supply": supply, "target": target}
    if step == room:
        return MixerAction(
            direction,
            seconds + settings.end_pulse,
            reason,
            end_pulse=True,
            why="supply",
            values=values,
        )
    return MixerAction(direction, seconds, reason, why="supply", values=values)


def hold_reason(
    *,
    demand: bool,
    target: float | None,
    supply: float | None,
    position: float | None,
    settings: MixerSettings,
    since_move: float | None = None,
    trend: float | None = None,
) -> tuple[str, dict[str, float]] | None:
    """Why regulate() stays, for Activity; None when there is nothing worth saying.

    Waiting for the last move to show is left out: it follows every move.
    """
    if not demand or position is None:
        return None
    if target is None:
        return "no_target", {}
    if supply is None:
        return "no_supply", {}
    values = {"supply": supply, "target": target, "position": position}
    if abs(target - supply) <= settings.hysteresis:
        return "band", values | {"hysteresis": settings.hysteresis}
    if since_move is not None and since_move < settings.settle:
        return None
    if trend is not None:
        expected = supply + trend * settings.settle / 60.0
        if (target - supply) * (target - expected) <= 0:
            return "heading", values | {"trend": trend}
    return None


def starved(
    *,
    heating: bool,
    demand: bool,
    position: float | None,
    supply: float | None,
    target: float | None,
    settings: MixerSettings,
) -> bool:
    """Fully open and still below the target: the water from the source is not enough."""
    if not (heating and demand) or position is None or supply is None or target is None:
        return False
    return position >= 99.0 and supply < target - settings.hysteresis
