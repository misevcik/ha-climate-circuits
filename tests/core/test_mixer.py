"""Mixing valve regulation."""

from __future__ import annotations

import pytest

from custom_components.climate_circuits.core.mixer import (
    Direction,
    MixerSettings,
    advance,
    regulate,
    step_size,
)

S = MixerSettings(travel=100.0, hysteresis=0.5)


def _regulate(**kwargs):
    args = {
        "heating": True,
        "demand": True,
        "target": 35.0,
        "supply": 35.0,
        "position": 50.0,
        "since_end_pulse": None,
        "settings": S,
    }
    args.update(kwargs)
    return regulate(**args)


def test_advance_clamps() -> None:
    assert advance(50.0, Direction.OPEN, 10.0, 100.0) == 60.0
    assert advance(5.0, Direction.CLOSE, 10.0, 100.0) == 0.0
    assert advance(98.0, Direction.OPEN, 10.0, 100.0) == 100.0


@pytest.mark.parametrize(("diff", "step"), [(0.6, 6), (1.4, 6), (2.5, 8), (-3.0, 8), (12.0, 10)])
def test_step_size_like_mixerautomation(diff: float, step: int) -> None:
    assert step_size(diff, S) == step


def test_within_hysteresis_does_nothing() -> None:
    assert _regulate(supply=34.6) is None


def test_heating_too_cold_opens() -> None:
    action = _regulate(supply=33.0)
    assert action.direction is Direction.OPEN
    assert action.seconds == pytest.approx(7.0)
    assert not action.end_pulse


def test_heating_too_warm_closes() -> None:
    assert _regulate(supply=37.0).direction is Direction.CLOSE


def test_cooling_too_warm_opens() -> None:
    action = _regulate(heating=False, target=18.0, supply=20.0)
    assert action.direction is Direction.OPEN


def test_step_capped_at_end_stop_runs_on() -> None:
    action = _regulate(supply=30.0, position=97.0)
    assert action.direction is Direction.OPEN
    assert action.seconds == pytest.approx(3.0 + S.end_pulse)
    assert action.end_pulse


def test_end_pulse_rate_limited() -> None:
    assert _regulate(supply=30.0, position=100.0, since_end_pulse=60.0) is None
    action = _regulate(supply=30.0, position=100.0, since_end_pulse=601.0)
    assert action.end_pulse
    assert action.seconds == S.end_pulse
    assert _regulate(supply=30.0, position=100.0, since_end_pulse=None).end_pulse


def test_no_demand_closes_fully() -> None:
    action = _regulate(demand=False, position=40.0)
    assert action.direction is Direction.CLOSE
    assert action.seconds == pytest.approx(40.0 + S.end_pulse)


def test_no_demand_closed_valve_only_pulses_rarely() -> None:
    assert _regulate(demand=False, position=0.0, since_end_pulse=30.0) is None
    assert _regulate(demand=False, position=0.0, since_end_pulse=700.0).end_pulse


def test_missing_sensor_holds_position() -> None:
    assert _regulate(supply=None) is None
    assert _regulate(target=None) is None


def test_unknown_position_homes() -> None:
    action = _regulate(position=None)
    assert action.homing
    assert action.direction is Direction.CLOSE
    assert action.seconds == S.travel + S.end_pulse
