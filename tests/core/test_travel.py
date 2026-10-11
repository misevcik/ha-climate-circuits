"""Valve position from relay run times."""

from __future__ import annotations

import pytest

from custom_components.climate_circuits.core.mixer import Direction
from custom_components.climate_circuits.core.travel import TravelTracker


def tracker(position: float | None = 0.0) -> TravelTracker:
    return TravelTracker(travel_open=125.0, travel_close=125.0, position=position)


def test_opening_follows_run_time() -> None:
    t = tracker()
    t.start(Direction.OPEN, now=10.0)
    assert t.moving
    assert t.current(10.0 + 62.5) == pytest.approx(50.0)
    t.stop(10.0 + 12.5)
    assert t.position == pytest.approx(10.0)
    assert not t.moving
    assert t.current(1000.0) == pytest.approx(10.0)


def test_closing_and_clamping() -> None:
    t = tracker(50.0)
    t.start(Direction.CLOSE, now=0.0)
    assert t.current(25.0) == pytest.approx(30.0)
    t.stop(500.0)  # a long run: against the end stop
    assert t.position == 0.0
    t.start(Direction.OPEN, now=0.0)
    t.stop(500.0)
    assert t.position == 100.0


def test_different_open_and_close_times() -> None:
    t = TravelTracker(travel_open=100.0, travel_close=200.0, position=50.0)
    t.start(Direction.OPEN, now=0.0)
    assert t.current(25.0) == pytest.approx(75.0)
    t.start(Direction.CLOSE, now=25.0)  # turning round stops the first move
    assert t.current(25.0 + 50.0) == pytest.approx(50.0)


def test_unknown_position_stays_unknown_until_set() -> None:
    t = tracker(None)
    t.start(Direction.OPEN, now=0.0)
    t.stop(50.0)
    assert t.position is None
    t.set(0.0)
    assert t.current(99.0) == 0.0
    t.clear()
    assert t.current(0.0) is None
