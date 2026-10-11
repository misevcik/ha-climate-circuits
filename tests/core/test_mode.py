"""Mode resolution."""

from __future__ import annotations

import pytest

from custom_components.climate_circuits.core.mode import (
    EntityMapping,
    FallbackKind,
    Mode,
    ModeSettings,
    ModeSource,
    Override,
    mode_from_entity,
    resolve_mode,
)

HEAT_PUMP = ModeSettings(
    capabilities=frozenset({Mode.HEAT, Mode.COOL}),
    fallback=FallbackKind.TANK,
    heat_threshold=28.0,
    cool_threshold=22.0,
)
BOILER = ModeSettings(
    capabilities=frozenset({Mode.HEAT}),
    fallback=FallbackKind.OUTDOOR,
    heat_threshold=15.0,
    cool_threshold=24.0,
)


@pytest.mark.parametrize(
    ("domain", "state", "expected"),
    [
        ("climate", "heat", Mode.HEAT),
        ("climate", "cool", Mode.COOL),
        ("climate", "off", Mode.OFF),
        ("climate", "auto", None),
        ("climate", "unavailable", None),
        ("binary_sensor", "on", Mode.HEAT),
        ("switch", "off", Mode.OFF),
        ("input_boolean", "unknown", None),
        ("select", "Zima", Mode.HEAT),
        ("sensor", "Leto", Mode.COOL),
        ("input_select", "Vypnuté", Mode.OFF),
        ("select", "Iné", None),
        ("climate", None, None),
    ],
)
def test_mode_from_entity(domain: str, state: str | None, expected: Mode | None) -> None:
    mapping = EntityMapping(heat=["Zima"], cool=["Leto"], off=["Vypnuté"])
    assert mode_from_entity(domain, state, mapping) is expected


def test_override_wins() -> None:
    decision = resolve_mode(HEAT_PUMP, Override.COOL, Mode.HEAT, 40.0, Mode.HEAT)
    assert decision.mode is Mode.COOL
    assert decision.source is ModeSource.OVERRIDE


def test_override_beyond_capabilities_is_off() -> None:
    decision = resolve_mode(BOILER, Override.COOL, None, None, None)
    assert decision.mode is Mode.OFF
    assert "not supported" in decision.reason


def test_entity_before_fallback() -> None:
    decision = resolve_mode(HEAT_PUMP, Override.AUTO, Mode.COOL, 40.0, Mode.HEAT)
    assert decision.mode is Mode.COOL
    assert decision.source is ModeSource.ENTITY


def test_entity_mode_beyond_capabilities_is_off() -> None:
    decision = resolve_mode(BOILER, Override.AUTO, Mode.COOL, None, Mode.HEAT)
    assert decision.mode is Mode.OFF


@pytest.mark.parametrize(
    ("tank", "last", "expected"),
    [
        (28.0, None, Mode.HEAT),
        (35.0, Mode.COOL, Mode.HEAT),
        (22.0, Mode.HEAT, Mode.COOL),
        (25.0, Mode.HEAT, Mode.HEAT),
        (25.0, Mode.COOL, Mode.COOL),
    ],
)
def test_tank_fallback_with_hysteresis(tank: float, last: Mode | None, expected: Mode) -> None:
    decision = resolve_mode(HEAT_PUMP, Override.AUTO, None, tank, last)
    assert decision.mode is expected


def test_tank_between_thresholds_without_history_is_off() -> None:
    decision = resolve_mode(HEAT_PUMP, Override.AUTO, None, 25.0, None)
    assert decision.mode is Mode.OFF
    assert decision.source is ModeSource.DEFAULT


@pytest.mark.parametrize(
    ("outdoor", "expected"),
    [(10.0, Mode.HEAT), (15.0, Mode.HEAT), (18.0, Mode.OFF), (30.0, Mode.OFF)],
)
def test_outdoor_fallback_respects_capabilities(outdoor: float, expected: Mode) -> None:
    # 30 °C would mean cooling, but the boiler cannot cool.
    decision = resolve_mode(BOILER, Override.AUTO, None, outdoor, Mode.HEAT)
    assert decision.mode is expected
    assert decision.source is ModeSource.FALLBACK


def test_last_mode_when_nothing_is_available() -> None:
    decision = resolve_mode(HEAT_PUMP, Override.AUTO, None, None, Mode.COOL)
    assert decision.mode is Mode.COOL
    assert decision.source is ModeSource.LAST
