"""Mixing valve regulation."""

from __future__ import annotations

import pytest

from custom_components.climate_circuits.core.mixer import (
    Direction,
    MixerSettings,
    advance,
    regulate,
    source_compensation,
    step_size,
    supply_trend,
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


@pytest.mark.parametrize(("diff", "step"), [(0.6, 2), (1.4, 6), (2.5, 10), (-3.0, 12), (12.0, 20)])
def test_step_grows_with_the_difference(diff: float, step: int) -> None:
    assert step_size(diff, S) == step


def test_within_hysteresis_does_nothing() -> None:
    assert _regulate(supply=34.6) is None


def test_heating_too_cold_opens() -> None:
    action = _regulate(supply=33.0)
    assert action.direction is Direction.OPEN
    assert action.seconds == pytest.approx(8.0)  # 2 K x 4 %/K of a 100 s travel
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
    assert _regulate(demand=False, position=0.0, since_end_pulse=700.0) is None
    assert _regulate(demand=False, position=0.0, since_end_pulse=S.idle_pulse_interval).end_pulse


def test_waits_after_a_move_until_it_reaches_the_sensor() -> None:
    assert _regulate(supply=33.0, since_move=S.settle - 1) is None
    assert _regulate(supply=33.0, since_move=S.settle).direction is Direction.OPEN


def test_no_move_while_the_supply_already_heads_for_the_target() -> None:
    # 2 K below, rising 1 K/min: there within the settle time
    assert _regulate(supply=33.0, trend=1.0) is None
    # rising too slowly, or falling: help it
    assert _regulate(supply=33.0, trend=0.2).direction is Direction.OPEN
    assert _regulate(supply=33.0, trend=-0.5).direction is Direction.OPEN
    # too warm and already cooling fast
    assert _regulate(supply=37.0, trend=-1.0) is None


def test_trend_from_readings() -> None:
    samples = [(0.0, 30.0), (60.0, 30.5), (120.0, 31.0)]
    assert supply_trend(samples, 120.0, 120.0) == pytest.approx(0.5)
    assert supply_trend(samples[:1], 0.0, 120.0) is None  # not enough history
    assert supply_trend([(100.0, 30.0), (120.0, 30.2)], 120.0, 120.0) is None


def test_missing_sensor_holds_position() -> None:
    assert _regulate(supply=None) is None
    assert _regulate(target=None) is None


def test_unknown_position_homes() -> None:
    action = _regulate(position=None)
    assert action.homing
    assert action.direction is Direction.CLOSE
    assert action.seconds == S.travel + S.end_pulse


def test_source_compensation_keeps_the_supply() -> None:
    # 40 % open, source 45, supply 31: return = (31 - 0.4 x 45) / 0.6 = 21.67
    change = source_compensation(40.0, 31.0, 48.0, 45.0, S)
    # check against the mixing model: the new position gives the old supply at the new source
    p = 0.4 + change / 100.0
    ret = (31.0 - 0.4 * 45.0) / 0.6
    assert ret + (48.0 - ret) * p == pytest.approx(31.0, abs=0.3)
    assert change < 0
    assert source_compensation(40.0, 31.0, 42.0, 45.0, S) > 0
    assert source_compensation(0.0, 31.0, 48.0, 45.0, S) is None  # closed: nothing to scale
    assert source_compensation(40.0, 31.0, 32.0, 30.0, S) is None  # source barely above supply


def test_source_change_moves_at_once_even_while_settling() -> None:
    action = _regulate(supply=35.0, source=50.0, source_ref=45.0, since_move=10.0)
    assert action.direction is Direction.CLOSE
    assert "source 45.0 -> 50.0" in action.reason
    # a small source change is left to the supply regulation
    assert _regulate(supply=35.0, source=45.2, source_ref=45.0) is None
    # without a reference (sensor just appeared) nothing is compensated
    assert _regulate(supply=35.0, source=50.0, source_ref=None) is None


def test_no_source_compensation_close_to_the_supply() -> None:
    # the tank fell to 38 for a supply of 35: steps would blow up, the supply regulation acts
    assert _regulate(target=35.0, supply=35.0, source=38.0, source_ref=44.0) is None
