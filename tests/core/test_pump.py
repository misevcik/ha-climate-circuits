"""Circuit pump timing."""

from __future__ import annotations

from custom_components.climate_circuits.core.pump import PumpReason as R, PumpTimer


def decide(timer: PumpTimer, now: float, demand: bool, heating: bool = True, running: bool = False):
    return timer.update(now, demand, run_on_allowed=heating, running=running)


def test_waits_for_the_valves_then_runs() -> None:
    timer = PumpTimer(delay=180, run_on=180)
    first = decide(timer, 0, True)
    assert (first.on, first.reason, first.remaining) == (False, R.WAITING, 180)
    assert decide(timer, 100, True).remaining == 80
    started = decide(timer, 180, True)
    assert (started.on, started.reason) == (True, R.RUNNING)


def test_demand_that_goes_away_resets_the_wait() -> None:
    timer = PumpTimer(delay=180, run_on=0)
    decide(timer, 0, True)
    assert decide(timer, 100, False).reason is R.IDLE
    assert decide(timer, 110, True).remaining == 180


def test_runs_on_while_heating_and_stops_at_once_while_cooling() -> None:
    timer = PumpTimer(delay=0, run_on=180)
    assert decide(timer, 0, True).on
    runon = decide(timer, 10, False)
    assert (runon.on, runon.reason, runon.remaining) == (True, R.RUN_ON, 180)
    assert decide(timer, 100, False).remaining == 90
    assert not decide(timer, 190, False).on

    timer = PumpTimer(delay=0, run_on=180)
    decide(timer, 0, True, heating=False)
    assert decide(timer, 10, False, heating=False).reason is R.IDLE


def test_a_pump_that_already_runs_is_not_made_to_wait() -> None:
    timer = PumpTimer(delay=180, run_on=0)
    assert decide(timer, 0, True, running=True).on


def test_a_pump_seen_running_while_waiting_is_kept_on() -> None:
    # After a restart the relay board connects late: demand first, then the running pump.
    timer = PumpTimer(delay=180, run_on=0)
    assert not decide(timer, 0, True).on
    assert decide(timer, 2, True, running=True).on


def test_exercise_runs_an_idle_pump() -> None:
    timer = PumpTimer(delay=180, run_on=180)
    decision = timer.update(0, False, True, running=False, exercise_left=45)
    assert (decision.on, decision.reason, decision.remaining) == (True, R.EXERCISE, 45)


def test_run_on_is_not_restarted_while_the_relay_still_reports_on() -> None:
    timer = PumpTimer(delay=0, run_on=180)
    decide(timer, 0, True)
    assert decide(timer, 10, False).on
    assert not decide(timer, 190, False, running=True).on  # run-on over, stop sent
    stopped = decide(timer, 190.01, False, running=True)  # relay not off yet
    assert (stopped.on, stopped.reason) == (False, R.IDLE)


def test_no_run_on_after_an_exercise() -> None:
    timer = PumpTimer(delay=180, run_on=180)
    timer.update(0, False, True, running=False, exercise_left=60)
    after = timer.update(60, False, True, running=True)
    assert (after.on, after.reason) == (False, R.IDLE)
