"""Circuit demand."""

from __future__ import annotations

from custom_components.climate_circuits.core.demand import circuit_demand
from custom_components.climate_circuits.core.mode import Mode

HEAT = ["climate.office", "climate.kitchen"]
COOL = ["climate.office_ac", "climate.kitchen_ac"]


def test_off_mode_never_demands() -> None:
    assert not circuit_demand(Mode.OFF, HEAT, COOL, {"climate.office": "heating"}).active


def test_heating_zone_calls() -> None:
    demand = circuit_demand(
        Mode.HEAT, HEAT, COOL, {"climate.office": "heating", "climate.kitchen": "idle"}
    )
    assert demand.active
    assert demand.zones == ("climate.office",)


def test_uses_list_of_current_mode() -> None:
    actions = {"climate.office": "heating", "climate.office_ac": "idle"}
    assert not circuit_demand(Mode.COOL, HEAT, COOL, actions).active
    actions["climate.kitchen_ac"] = "cooling"
    assert circuit_demand(Mode.COOL, HEAT, COOL, actions).zones == ("climate.kitchen_ac",)


def test_unavailable_thermostat_does_not_call() -> None:
    assert not circuit_demand(Mode.HEAT, HEAT, COOL, {"climate.office": None}).active


def test_circuit_without_zones_runs_with_mode() -> None:
    assert circuit_demand(Mode.HEAT, [], [], {}).active
    assert circuit_demand(Mode.COOL, [], [], {}).active
    assert not circuit_demand(Mode.OFF, [], [], {}).active
