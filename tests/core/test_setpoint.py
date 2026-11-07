"""The heat source setting from the circuits: warmest target + margin, rarely changed."""

from __future__ import annotations

from custom_components.climate_circuits.core.setpoint import (
    MarginSettings,
    SetpointSettings,
    next_margin,
    setpoint_decision,
)

S = SetpointSettings(margin=5.0, minimum=30.0, maximum=55.0, step=1.0, interval=900.0)


def _decide(**kwargs):
    args = {
        "heating": True,
        "targets": {"F1": 34.2, "GF": 38.6},
        "current": 45.0,
        "since_change": None,
        "settings": S,
    }
    return setpoint_decision(**(args | kwargs))


def test_warmest_target_plus_margin_rounded_up_to_the_step() -> None:
    d = _decide()
    assert (d.wanted, d.change, d.circuit, d.target) == (44.0, True, "GF", 38.6)


def test_small_difference_is_not_worth_a_change() -> None:
    assert _decide(current=44.5).change is False


def test_within_the_limits() -> None:
    assert _decide(targets={"F1": 60.0}).wanted == 55.0
    assert _decide(targets={"F1": 20.0}).wanted == 30.0


def test_not_changed_again_too_soon() -> None:
    d = _decide(since_change=600.0)
    assert (d.change, d.reason) == (False, "wait")
    assert _decide(since_change=900.0).change is True


def test_left_alone_without_demand_or_heating() -> None:
    assert _decide(targets={}).reason == "no_demand"
    assert _decide(heating=False).reason == "not_heating"
    assert _decide(targets={}).change is False


M = MarginSettings(
    minimum=3.0, maximum=15.0, step=1.0, short_after=600, raise_after=1800, lower_after=3600
)


def _margin(margin=8.0, **kwargs):
    args = {
        "short_for": None,
        "plenty_for": None,
        "since_change": None,
        "can_raise": True,
        "settings": M,
    }
    return next_margin(margin, **(args | kwargs))


def test_margin_rises_when_the_water_stays_short_but_not_too_often() -> None:
    assert _margin(short_for=300) == (8.0, None)  # a moment, e.g. the bottom of a cycle
    assert _margin(short_for=600) == (9.0, "raise")
    assert _margin(short_for=600, since_change=600) == (8.0, None)  # the tank is heating up
    assert _margin(15.0, short_for=600) == (15.0, None)


def test_no_raise_when_the_setting_is_at_its_highest_anyway() -> None:
    assert _margin(short_for=3600, can_raise=False) == (8.0, None)


def test_margin_falls_after_an_hour_of_plenty_of_water() -> None:
    assert _margin(plenty_for=1800) == (8.0, None)
    assert _margin(plenty_for=3600) == (7.0, "lower")
    assert _margin(plenty_for=3600, since_change=1200) == (8.0, None)
    assert _margin(3.0, plenty_for=7200) == (3.0, None)
