"""Weather curves and dew point."""

from __future__ import annotations

import pytest

from custom_components.climate_circuits.core.curve import (
    Curve,
    dew_point,
    raw_value,
    water_target,
    worst_dew_point,
)
from custom_components.climate_circuits.core.mode import Mode

RADIATORS = Curve(room=22.0, minimum=35.0, maximum=50.0)
COOLING = Curve(room=24.0, minimum=16.0, maximum=22.0, slope=0.5)


def test_dew_point_reference_values() -> None:
    assert dew_point(25.0, 50.0) == pytest.approx(13.9, abs=0.1)
    assert dew_point(20.0, 100.0) == pytest.approx(20.0, abs=0.01)


def test_worst_dew_point_uses_warmest_and_most_humid() -> None:
    assert worst_dew_point([22.0, 26.0], [70.0, 40.0]) == pytest.approx(dew_point(26.0, 70.0))
    assert worst_dew_point([], [50.0]) is None


def test_heating_curve_passes_room_and_design_point() -> None:
    curve = Curve(room=22.0, minimum=0.0, maximum=90.0)
    assert raw_value(Mode.HEAT, curve, 22.0) == pytest.approx(22.0)
    assert raw_value(Mode.HEAT, curve, -15.0) == pytest.approx(50.0)
    # Warmer outside than inside: no load, water at room temperature.
    assert raw_value(Mode.HEAT, curve, 25.0) == pytest.approx(22.0)


def test_heating_curve_bends_like_emitters() -> None:
    # Halfway in load, the water is more than halfway up: the curve is concave.
    curve = Curve(room=22.0, minimum=0.0, maximum=90.0)
    half = raw_value(Mode.HEAT, curve, 22.0 - 37.0 / 2)
    assert half > (22.0 + 50.0) / 2
    floor = Curve(room=22.0, minimum=0.0, maximum=90.0, exponent=1.1)
    assert raw_value(Mode.HEAT, floor, 3.5) < half


def test_heating_curve_clamped_to_maximum() -> None:
    target = water_target(Mode.HEAT, RADIATORS, -20.0)
    assert target is not None
    assert target.value == 50.0
    assert target.reason == "curve clamped to maximum"


def test_heating_curve_with_correction() -> None:
    curve = Curve(room=22.0, minimum=30.0, maximum=50.0, correction=1.0)
    target = water_target(Mode.HEAT, curve, 0.0)
    assert target is not None
    assert target.value == 41.8
    assert target.reason == "curve"


def test_correction_applies_before_clamping() -> None:
    curve = Curve(room=22.0, minimum=35.0, maximum=50.0, correction=-20.0)
    target = water_target(Mode.HEAT, curve, 0.0)
    assert target is not None
    assert target.value == 35.0


def test_missing_outdoor_uses_gentlest_value() -> None:
    assert water_target(Mode.HEAT, RADIATORS, None).value == 35.0
    assert water_target(Mode.COOL, COOLING, None).value == 22.0


def test_cooling_curve() -> None:
    target = water_target(Mode.COOL, COOLING, 32.0)
    assert target is not None
    assert target.value == 20.0


def test_cooling_never_below_dew_point_margin() -> None:
    target = water_target(Mode.COOL, COOLING, 40.0, dew=19.5)
    assert target is not None
    # Curve says 16 °C, dew point + 2 K is 21.5 °C.
    assert target.value == 21.5
    assert target.reason.startswith("dew point")


def test_dew_point_floor_beats_maximum() -> None:
    target = water_target(Mode.COOL, COOLING, 30.0, dew=21.0)
    assert target is not None
    assert target.value == 23.0


def test_off_has_no_target() -> None:
    assert water_target(Mode.OFF, RADIATORS, 0.0) is None
