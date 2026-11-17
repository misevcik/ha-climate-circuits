"""Hot water circulation pump: hysteresis on the circulation return temperature.

The pump stops at the threshold, but never above the tank less a margin: the water coming back
can not get warmer than the tank it came from. A run that does not reach it within the longest
run stops for a pause. A schedule, when set, allows the pump only within its times.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CirculationReason(StrEnum):
    COLD = "cold"  # below threshold − delta: start
    WARMING = "warming"  # running, below threshold: keep running
    REACHED = "reached"  # at threshold: stop
    WAITING = "waiting"  # stopped inside the band
    PAUSED = "paused"  # ran the longest run without reaching the threshold: pause
    OUTSIDE_SCHEDULE = "outside_schedule"
    DISABLED = "disabled"
    NO_SENSOR = "no_sensor"


# Not running for a reason other than the temperature, with the state it shows; logged.
HELD_STATE = {
    CirculationReason.PAUSED: "paused",
    CirculationReason.OUTSIDE_SCHEDULE: "outside_schedule",
    CirculationReason.DISABLED: "disabled",
    CirculationReason.NO_SENSOR: "unavailable",
}
# Decided by the temperatures: the message tells where it stops, and whether from the tank.
FROM_TEMPERATURE = frozenset(CirculationReason) - {
    CirculationReason.OUTSIDE_SCHEDULE,
    CirculationReason.DISABLED,
    CirculationReason.NO_SENSOR,
}


@dataclass(frozen=True, slots=True)
class CirculationDecision:
    on: bool
    reason: CirculationReason
    temperature: float | None
    on_below: float
    off_at: float
    tank_limited: bool = False  # the stop temperature follows the tank, not the threshold
    max_run: float = 0  # s, 0: no limit
    pause_left: float = 0  # s; a pause runs out whatever else holds the pump
    pause_started: bool = False  # this decision begins a pause


# A tank reading below this is a sensor fault (e.g. 0 or -127 °C), not hot water: ignored.
TANK_PLAUSIBLE_MIN = 5.0


def stop_temperature(threshold: float, tank: float | None, margin: float) -> float:
    """The threshold, or the tank less the margin when that is lower."""
    if tank is None or tank < TANK_PLAUSIBLE_MIN:
        return threshold
    return min(threshold, round(tank - margin, 1))


def circulation_decision(
    temperature: float | None,
    threshold: float,
    delta: float,
    running: bool,
    enabled: bool,
    *,
    tank: float | None = None,
    tank_margin: float = 0.0,
    allowed: bool = True,
    ran_for: float | None = None,
    paused_for: float | None = None,
    max_run: float = 0.0,
    pause: float = 0.0,
) -> CirculationDecision:
    """ran_for: s the pump has been running; paused_for: s since a pause began, None if none.

    max_run and pause in s; the limit applies only when both are above 0. A pause runs out its
    time even while something else holds the pump (switched off, schedule, sensor); a change of
    the limit applies to it at once.
    """
    off_at = stop_temperature(threshold, tank, tank_margin)
    limit = max_run > 0 and pause > 0
    pausing = limit and paused_for is not None and paused_for < pause
    pause_left = pause - paused_for if pausing and paused_for is not None else 0.0
    started = False
    if not enabled:
        on, reason = False, CirculationReason.DISABLED
    elif not allowed:
        on, reason = False, CirculationReason.OUTSIDE_SCHEDULE
    elif temperature is None:
        on, reason = False, CirculationReason.NO_SENSOR
    elif pausing:
        on, reason = False, CirculationReason.PAUSED
    elif temperature >= off_at:
        on, reason = False, CirculationReason.REACHED
    elif limit and running and ran_for is not None and ran_for >= max_run:
        on, reason, pause_left, started = False, CirculationReason.PAUSED, pause, True
    elif temperature < off_at - delta:
        on, reason = True, CirculationReason.COLD
    elif running:
        on, reason = True, CirculationReason.WARMING
    else:
        on, reason = False, CirculationReason.WAITING
    if reason not in FROM_TEMPERATURE:
        off_at = threshold  # held for another reason: show the set threshold, not the tank's
    return CirculationDecision(
        on,
        reason,
        temperature,
        round(off_at - delta, 1),
        off_at,
        tank_limited=off_at < threshold and reason in FROM_TEMPERATURE,
        max_run=max_run if limit else 0.0,
        pause_left=pause_left,
        pause_started=started,
    )
