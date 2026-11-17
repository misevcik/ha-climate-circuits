"""Hot water circulation hysteresis."""

from __future__ import annotations

import pytest

from custom_components.climate_circuits.core.circulation import (
    CirculationReason as R,
    circulation_decision,
)


@pytest.mark.parametrize(
    ("temperature", "running", "on", "reason"),
    [
        (35.9, False, True, R.COLD),
        (35.9, True, True, R.COLD),
        (36.5, True, True, R.WARMING),
        (36.5, False, False, R.WAITING),
        (36.0, False, False, R.WAITING),
        (37.0, True, False, R.REACHED),
        (40.0, False, False, R.REACHED),
        (None, True, False, R.NO_SENSOR),
    ],
)
def test_hysteresis(temperature, running, on, reason) -> None:
    decision = circulation_decision(temperature, 37.0, 1.0, running, enabled=True)
    assert (decision.on, decision.reason) == (on, reason)
    assert (decision.on_below, decision.off_at) == (36.0, 37.0)


def test_disabled_wins() -> None:
    decision = circulation_decision(20.0, 37.0, 1.0, running=True, enabled=False)
    assert (decision.on, decision.reason) == (False, R.DISABLED)


def test_the_tank_lowers_the_stop() -> None:
    """Water coming back can not be warmer than the tank: stop at the tank less the margin."""
    decision = circulation_decision(
        31.0, 36.0, 2.0, running=True, enabled=True, tank=36.0, tank_margin=5.0
    )
    assert (decision.on, decision.reason) == (False, R.REACHED)
    assert (decision.on_below, decision.off_at, decision.tank_limited) == (29.0, 31.0, True)


def test_a_warm_tank_keeps_the_threshold() -> None:
    decision = circulation_decision(
        33.0, 36.0, 2.0, running=False, enabled=True, tank=50.0, tank_margin=5.0
    )
    assert (decision.on, decision.off_at, decision.tank_limited) == (True, 36.0, False)


def test_a_run_too_long_pauses() -> None:
    decision = circulation_decision(
        33.0, 36.0, 2.0, running=True, enabled=True, ran_for=600, max_run=600, pause=1800
    )
    assert (decision.on, decision.reason, decision.pause_left) == (False, R.PAUSED, 1800)
    assert decision.pause_started


def test_a_shorter_run_goes_on() -> None:
    decision = circulation_decision(
        33.0, 36.0, 2.0, running=True, enabled=True, ran_for=599, max_run=600, pause=1800
    )
    assert (decision.on, decision.reason) == (True, R.COLD)


@pytest.mark.parametrize(("max_run", "pause"), [(0, 1800), (600, 0)])
def test_zero_turns_the_limit_off(max_run, pause) -> None:
    decision = circulation_decision(
        33.0, 36.0, 2.0, True, True, ran_for=10_000, paused_for=10, max_run=max_run, pause=pause
    )
    assert (decision.on, decision.max_run, decision.pause_left) == (True, 0, 0)


def test_a_pause_holds_a_cold_pump() -> None:
    decision = circulation_decision(
        30.0, 36.0, 2.0, running=False, enabled=True, paused_for=600, max_run=600, pause=1800
    )
    assert (decision.on, decision.reason, decision.pause_left) == (False, R.PAUSED, 1200)


def test_a_pause_ends() -> None:
    decision = circulation_decision(
        30.0, 36.0, 2.0, running=False, enabled=True, paused_for=1800, max_run=600, pause=1800
    )
    assert (decision.on, decision.reason) == (True, R.COLD)


def test_a_pause_runs_out_its_time() -> None:
    """Warm water, a switched off circulation or a lost sensor do not end it early."""
    kwargs = {"paused_for": 60, "max_run": 600, "pause": 1800}
    warm = circulation_decision(36.5, 36.0, 2.0, running=False, enabled=True, **kwargs)
    assert (warm.reason, warm.pause_left) == (R.PAUSED, 1740)
    off = circulation_decision(30.0, 36.0, 2.0, running=False, enabled=False, **kwargs)
    assert (off.reason, off.pause_left) == (R.DISABLED, 1740)
    lost = circulation_decision(None, 36.0, 2.0, running=False, enabled=True, **kwargs)
    assert (lost.reason, lost.pause_left) == (R.NO_SENSOR, 1740)


def test_a_pump_still_running_after_a_pause_starts_a_new_one() -> None:
    """Dry run: somebody else keeps the pump on; a new pause begins, not an endless one."""
    decision = circulation_decision(
        33.0, 36.0, 2.0, True, True, ran_for=2400, paused_for=1800, max_run=600, pause=1800
    )
    assert (decision.reason, decision.pause_started, decision.pause_left) == (
        R.PAUSED,
        True,
        1800,
    )


def test_outside_the_schedule() -> None:
    decision = circulation_decision(20.0, 36.0, 2.0, running=True, enabled=True, allowed=False)
    assert (decision.on, decision.reason) == (False, R.OUTSIDE_SCHEDULE)
    off = circulation_decision(20.0, 36.0, 2.0, running=True, enabled=False, allowed=False)
    assert off.reason is R.DISABLED


@pytest.mark.parametrize("tank", [0.0, -127.0])
def test_a_faulty_tank_reading_is_ignored(tank) -> None:
    decision = circulation_decision(35.0, 37.0, 1.0, False, True, tank=tank, tank_margin=5.0)
    assert (decision.off_at, decision.tank_limited, decision.on) == (37.0, False, True)


def test_held_for_another_reason_it_is_not_from_the_tank() -> None:
    decision = circulation_decision(30.0, 37.0, 1.0, False, False, tank=39.0, tank_margin=5.0)
    assert (decision.reason, decision.off_at, decision.tank_limited) == (R.DISABLED, 37.0, False)


def test_a_pause_says_so_when_the_circulation_warmed_up_meanwhile() -> None:
    from custom_components.climate_circuits.core.texts import circulation_message

    decision = circulation_decision(
        38.0, 37.0, 1.0, False, True, paused_for=60, max_run=600, pause=1800
    )
    assert decision.reason == R.PAUSED
    message = circulation_message(decision, "en", dry_run=False, until="14:35")
    assert message == "Paused – circulation 38.0 °C, stops at 37.0 °C, again at 14:35"
