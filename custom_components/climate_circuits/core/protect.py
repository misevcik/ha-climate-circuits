"""Protections: condensation while cooling, the pause between heating and cooling, exercising."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .mode import Mode


class Block(StrEnum):
    PAUSE = "pause"  # waiting after the other mode stopped
    DEW_POINT = "dew_point"  # water colder than the dew point + margin
    NO_HUMIDITY = "no_humidity"  # cooling without a dew point is not allowed


@dataclass(frozen=True, slots=True)
class Blocked:
    block: Block
    remaining: float = 0.0  # s, for the pause
    dew_point: float | None = None
    supply: float | None = None


class CondensationGuard:
    """Stops cooling when the water drops below dew point + stop_margin.

    Cooling is released at dew point + release_margin, and not before hold seconds passed.
    A missing dew point (no humidity data) blocks cooling.
    """

    def __init__(self, stop_margin: float = 2.0, release_margin: float = 3.0, hold: float = 300.0):
        self.stop_margin, self.release_margin, self.hold = stop_margin, release_margin, hold
        self._since: float | None = None

    def check(self, now: float, supply: float | None, dew_point: float | None) -> Blocked | None:
        if dew_point is None:
            return Blocked(Block.NO_HUMIDITY)
        if supply is None:
            return (
                Blocked(Block.DEW_POINT, dew_point=dew_point) if self._since is not None else None
            )
        if self._since is None:
            if supply >= dew_point + self.stop_margin:
                return None
            self._since = now
        elif supply >= dew_point + self.release_margin and now - self._since >= self.hold:
            self._since = None
            return None
        return Blocked(Block.DEW_POINT, dew_point=dew_point, supply=supply)


class ModePause:
    """Heating and cooling must not follow each other at once: the new mode waits seconds.

    Going back to the mode that ran last needs no pause. Wall-clock times, so it survives restarts.
    """

    def __init__(self, seconds: float, active: Mode | None = None, stopped_at: float | None = None):
        self.seconds, self.active, self.stopped_at = seconds, active, stopped_at

    def check(self, mode: Mode, now: float) -> float:
        """Seconds the mode still has to wait, 0 when it may run."""
        if mode is Mode.OFF:
            if self.active is not None and self.stopped_at is None:
                self.stopped_at = now
            return 0.0
        if self.active is None or mode is self.active:
            self.active, self.stopped_at = mode, None
            return 0.0
        if self.stopped_at is None:
            self.stopped_at = now
        remaining = self.stopped_at + self.seconds - now
        if remaining <= 0:
            self.active, self.stopped_at = mode, None
            return 0.0
        return remaining


def exercise_due(last: float | None, now: float, days: float) -> bool:
    """True when something has not run for days days; unknown history never triggers."""
    return days > 0 and last is not None and now - last >= days * 86400
