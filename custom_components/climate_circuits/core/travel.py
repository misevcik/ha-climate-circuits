"""Mixing valve position (0 closed … 100 open) tracked from relay run times.

Derived from the TravelCalculator of cover_time_based, itself derived from xknx (MIT licence).
The clock is passed in, so the tracker is testable and knows nothing about covers.
"""

from __future__ import annotations

from dataclasses import dataclass

from .mixer import Direction


@dataclass(slots=True)
class TravelTracker:
    """Position is None until it is known (homed, restored or seeded)."""

    travel_open: float
    travel_close: float
    position: float | None = None
    direction: Direction | None = None
    started: float = 0.0

    @property
    def moving(self) -> bool:
        return self.direction is not None

    def _travel(self, direction: Direction) -> float:
        return self.travel_open if direction is Direction.OPEN else self.travel_close

    def current(self, now: float) -> float | None:
        """Position now, including a move that is still running."""
        if self.position is None or self.direction is None:
            return self.position
        delta = 100.0 * max(now - self.started, 0.0) / self._travel(self.direction)
        moved = self.position + delta if self.direction is Direction.OPEN else self.position - delta
        return min(max(moved, 0.0), 100.0)

    def start(self, direction: Direction, now: float) -> None:
        self.stop(now)
        self.direction, self.started = direction, now

    def stop(self, now: float) -> None:
        self.position = self.current(now)
        self.direction = None

    def set(self, position: float) -> None:
        """A known position, e.g. after closing against the end stop."""
        self.position = min(max(position, 0.0), 100.0)
        self.direction = None

    def clear(self) -> None:
        self.position, self.direction = None, None
