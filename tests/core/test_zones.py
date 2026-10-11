"""Thermostat sets on a mode change."""

from __future__ import annotations

from custom_components.climate_circuits.core.mode import Mode
from custom_components.climate_circuits.core.zones import plan_zones

HEAT = ["climate.kitchen", "climate.office"]
COOL = ["climate.kitchen_cool", "climate.office_cool"]


def test_cooling_turns_heating_off_first() -> None:
    states = {"climate.kitchen": "heat", "climate.office": "off", **dict.fromkeys(COOL, "off")}
    plan = plan_zones(Mode.COOL, HEAT, COOL, states, switching=True)
    assert plan.turn_off == ("climate.kitchen",)
    assert plan.turn_on == tuple(COOL)
    assert plan.blocked
    assert plan.hvac_mode == "cool"


def test_switch_on_once_other_set_is_off() -> None:
    states = {**dict.fromkeys(HEAT, "off"), **dict.fromkeys(COOL, "off")}
    plan = plan_zones(Mode.COOL, HEAT, COOL, states, switching=True)
    assert plan.turn_off == ()
    assert not plan.blocked
    assert plan.turn_on == tuple(COOL)


def test_without_switching_only_keeps_other_set_off() -> None:
    states = {"climate.kitchen": "heat", "climate.office": "off", **dict.fromkeys(COOL, "off")}
    plan = plan_zones(Mode.COOL, HEAT, COOL, states, switching=False)
    assert plan.turn_off == ("climate.kitchen",)
    assert plan.turn_on == ()


def test_off_turns_everything_off() -> None:
    states = {"climate.kitchen": "heat", "climate.office_cool": "cool"}
    plan = plan_zones(Mode.OFF, HEAT, COOL, states, switching=False)
    assert set(plan.turn_off) == {"climate.kitchen", "climate.office_cool"}
    assert plan.hvac_mode is None


def test_shared_thermostat_is_switched_not_turned_off() -> None:
    plan = plan_zones(
        Mode.COOL, ["climate.living"], ["climate.living"], {"climate.living": "heat"}, True
    )
    assert plan.turn_off == ()
    assert plan.turn_on == ("climate.living",)


def test_unavailable_is_reported_not_commanded() -> None:
    plan = plan_zones(Mode.COOL, HEAT, COOL, {"climate.kitchen": None}, switching=False)
    assert "climate.kitchen" not in plan.turn_off
    assert "climate.kitchen" in plan.unavailable
