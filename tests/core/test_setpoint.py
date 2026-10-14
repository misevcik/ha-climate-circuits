"""The heat source setting from the circuits: warmest target + margin, rarely changed."""

from __future__ import annotations

from custom_components.climate_circuits.core.setpoint import SetpointSettings, setpoint_decision

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
