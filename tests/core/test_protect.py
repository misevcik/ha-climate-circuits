"""Condensation guard, mode pause and exercise."""

from __future__ import annotations

from custom_components.climate_circuits.core.mode import Mode
from custom_components.climate_circuits.core.protect import (
    Block,
    CondensationGuard,
    ModePause,
    exercise_due,
)


def test_cooling_without_humidity_is_blocked() -> None:
    assert CondensationGuard().check(0, 18.0, None).block is Block.NO_HUMIDITY


def test_stops_below_dew_point_plus_two_and_releases_after_the_hold() -> None:
    guard = CondensationGuard(hold=300)
    assert guard.check(0, 16.0, 12.0) is None  # 4 K above the dew point
    blocked = guard.check(10, 13.5, 12.0)  # below 12 + 2
    assert blocked.block is Block.DEW_POINT and blocked.supply == 13.5
    assert guard.check(100, 16.0, 12.0) is not None  # warm enough, but held
    assert guard.check(400, 14.5, 12.0) is not None  # held no more, but below 12 + 3
    assert guard.check(500, 15.5, 12.0) is None


def test_unknown_supply_does_not_block_a_free_circuit() -> None:
    assert CondensationGuard().check(0, None, 12.0) is None


def test_mode_pause_between_heating_and_cooling() -> None:
    pause = ModePause(3600)
    assert pause.check(Mode.HEAT, 0) == 0
    assert pause.check(Mode.COOL, 100) == 3600  # the pause starts when the change is seen
    assert pause.check(Mode.COOL, 1100) == 2600
    assert pause.check(Mode.COOL, 3700) == 0
    assert pause.active is Mode.COOL


def test_mode_pause_is_not_needed_when_going_back() -> None:
    pause = ModePause(3600)
    pause.check(Mode.HEAT, 0)
    pause.check(Mode.COOL, 10)
    assert pause.check(Mode.HEAT, 20) == 0


def test_mode_pause_counts_from_when_the_old_mode_stopped() -> None:
    pause = ModePause(3600)
    pause.check(Mode.HEAT, 0)
    pause.check(Mode.OFF, 100)  # stops here
    assert pause.check(Mode.COOL, 3000) == 700
    assert pause.check(Mode.COOL, 3800) == 0


def test_no_pause_when_it_is_off_and_the_first_mode_is_free() -> None:
    assert ModePause(0).check(Mode.HEAT, 0) == 0
    pause = ModePause(0)
    pause.check(Mode.HEAT, 0)
    assert pause.check(Mode.COOL, 1) == 0


def test_exercise_due() -> None:
    day = 86400
    assert exercise_due(0, 7 * day, 7)
    assert not exercise_due(0, 6 * day, 7)
    assert not exercise_due(None, 99 * day, 7)
    assert not exercise_due(0, 99 * day, 0)
