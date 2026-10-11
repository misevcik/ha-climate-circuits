"""Why a circuit heats or not."""

from __future__ import annotations

from custom_components.climate_circuits.core.demand import Demand
from custom_components.climate_circuits.core.explain import (
    CircuitState,
    ZoneSnapshot,
    ZoneStatus,
    explain_circuit,
    zone_status,
)
from custom_components.climate_circuits.core.mode import Mode
from custom_components.climate_circuits.core.texts import circuit_reason, zone_text


def _zone(name: str, **kwargs) -> ZoneSnapshot:
    args = {"available": True, "hvac_mode": "heat", "hvac_action": "idle"}
    args.update(kwargs)
    return ZoneSnapshot(f"climate.{name.lower()}", name, **args)


KITCHEN = _zone("Kitchen", hvac_action="heating", current=21.3, target=22.0)
OFFICE = _zone("Office", current=22.4, target=22.0)
BEDROOM = _zone("Bedroom", current=21.9, target=22.0)
BATH = _zone("Bath", hvac_mode="off", hvac_action="off", current=20.0, target=24.0)
HALL = _zone("Hall", available=False)


def test_zone_status() -> None:
    assert zone_status(Mode.HEAT, KITCHEN) is ZoneStatus.CALLING
    assert zone_status(Mode.HEAT, OFFICE) is ZoneStatus.SATISFIED
    assert zone_status(Mode.HEAT, BEDROOM) is ZoneStatus.WAITING
    assert zone_status(Mode.HEAT, BATH) is ZoneStatus.OFF
    assert zone_status(Mode.HEAT, HALL) is ZoneStatus.UNAVAILABLE
    cool = _zone("Cool", hvac_mode="cool", current=24.0, target=25.0)
    assert zone_status(Mode.COOL, cool) is ZoneStatus.SATISFIED


def test_heating_names_calling_zones() -> None:
    e = explain_circuit(Mode.HEAT, [KITCHEN, OFFICE, BATH], Demand(True, ("climate.kitchen",)))
    assert e.state is CircuitState.HEATING
    assert circuit_reason(e, "sk") == "Kúri – 1 z 3 zón: Kitchen"
    assert zone_text(e.zones[0], Mode.HEAT, "sk") == "kúri 21.3 °C → 22.0 °C"


def test_idle_counts_why_zones_do_not_call() -> None:
    e = explain_circuit(Mode.HEAT, [OFFICE, BEDROOM, BATH, HALL], Demand(False))
    assert e.state is CircuitState.IDLE
    assert circuit_reason(e, "sk") == (
        "Nekúri – žiadna zóna nepožaduje teplo: 1 má teplotu, 1 čaká v tolerancii, "
        "1 vypnuté, 1 nedostupné"
    )
    assert zone_text(e.zones[2], Mode.HEAT, "sk") == "termostat vypnutý"
    assert circuit_reason(e, "en").startswith("Not heating – no zone asks for heat")


def test_house_off() -> None:
    e = explain_circuit(Mode.OFF, [OFFICE], Demand(False))
    assert e.state is CircuitState.OFF
    assert circuit_reason(e, "sk", "override off") == (
        "Vypnuté – režim domu je vypnutý (override off)"
    )


def test_circuit_without_zones() -> None:
    e = explain_circuit(Mode.HEAT, [], Demand(True))
    assert circuit_reason(e, "en") == (
        "Heating – the circuit has no zones for this mode and runs with the house mode"
    )
