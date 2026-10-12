"""Circuit pump: starts once demand lasted long enough for the valves to open, runs on after."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PumpReason(StrEnum):
    RUNNING = "running"  # demand lasted long enough
    WAITING = "waiting"  # demand, valves still opening
    RUN_ON = "run_on"  # demand ended, pump runs on
    IDLE = "idle"  # no demand
    EXERCISE = "exercise"  # periodic run against seizing


@dataclass(frozen=True, slots=True)
class PumpDecision:
    on: bool
    reason: PumpReason
    remaining: float = 0.0  # s left of the delay, run-on or exercise


class PumpTimer:
    """delay: s of demand before the pump starts; run_on: s it keeps running after demand."""

    def __init__(self, delay: float, run_on: float) -> None:
        self.delay, self.run_on = delay, run_on
        self._demand_since: float | None = None
        self._demand_ended: float | None = None
        self._on = False

    def update(
        self,
        now: float,
        demand: bool,
        run_on_allowed: bool,
        running: bool,
        exercise_left: float = 0.0,
    ) -> PumpDecision:
        """running: the pump is already on (e.g. after a restart), so nothing is waited for."""
        if demand:
            self._demand_ended = None
            if self._demand_since is None:
                self._demand_since = now - self.delay if running else now
            left = self._demand_since + self.delay - now
            self._on = left <= 0
            return PumpDecision(
                self._on, PumpReason.RUNNING if self._on else PumpReason.WAITING, max(left, 0.0)
            )
        self._demand_since = None
        # Only a pump that ran for demand runs on. A relay still reporting on (the stop is
        # not confirmed yet, or an exercise just ended) must not start another run-on.
        if self._on and run_on_allowed and self.run_on > 0:
            if self._demand_ended is None:
                self._demand_ended = now
            left = self._demand_ended + self.run_on - now
            if left > 0:
                self._on = True
                return PumpDecision(True, PumpReason.RUN_ON, left)
        self._demand_ended = None
        self._on = False
        if exercise_left > 0:
            return PumpDecision(True, PumpReason.EXERCISE, exercise_left)
        return PumpDecision(False, PumpReason.IDLE)
