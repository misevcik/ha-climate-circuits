"""Circuit pump and mixing valve: dry run, live control, protections, command confirmation."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.climate_circuits.const import EVENT_ACTIVITY

from .conftest import HEAT_PUMP, circuit_data, set_thermostat, source_data

ZONE = "climate.living"
PUMP = "switch.f1_pump_relay"
OPEN = "switch.f1_open"
CLOSE = "switch.f1_close"
SUPPLY = "sensor.f1_supply"
SOURCE = "sensor.f1_source"
PUMP_SENSOR = "binary_sensor.f1_pump"
POSITION = "sensor.f1_mixer_position"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.wall = 1_700_000_000.0


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def calls(hass: HomeAssistant, house) -> list[tuple[str, str]]:
    """Relays that follow their commands."""
    calls: list[tuple[str, str]] = []

    async def handler(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        calls.append((call.service, entity_id))
        hass.states.async_set(entity_id, "on" if call.service == "turn_on" else "off")

    for service in ("turn_on", "turn_off"):
        hass.services.async_register("switch", service, handler)

    async def thermostat(call: ServiceCall) -> None:
        return None

    hass.services.async_register("climate", "set_hvac_mode", thermostat)
    return calls


@pytest.fixture
async def house(hass: HomeAssistant, make_entry, clock: Clock):
    hass.states.async_set(HEAT_PUMP, "heat")
    for relay in (PUMP, OPEN, CLOSE):
        hass.states.async_set(relay, "off")
    hass.states.async_set(SUPPLY, "30.0")
    hass.states.async_set(SOURCE, "45.0")
    set_thermostat(hass, ZONE, "idle")
    entry = make_entry(
        circuit_data(
            "F1",
            zones={"heating_zones": [ZONE]},
            outputs={
                "pump": PUMP,
                "mixer_open": OPEN,
                "mixer_close": CLOSE,
                "supply_sensor": SUPPLY,
                "pump_delay": 180,
                "pump_run_on": 180,
                "travel": 100,
            },
        ),
        source_data("Tank", SOURCE),
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    house = entry.runtime_data
    house.now = lambda: clock.now
    house.wall = lambda: clock.wall
    house.started = clock.now
    return house


async def _tick(hass: HomeAssistant, house, clock: Clock, seconds: float = 0.0) -> None:
    clock.now += seconds
    clock.wall += seconds
    house.evaluate()
    await hass.async_block_till_done()


async def _control(hass: HomeAssistant, on: bool, circuits: bool = True) -> None:
    house = next(iter(hass.config_entries.async_entries("climate_circuits"))).runtime_data
    for circuit in house.circuits.values():
        circuit.set_enabled(on and circuits)
    house.set_control_equipment(on)
    await hass.async_block_till_done()


async def test_dry_run_shows_the_pump_but_switches_nothing(hass, house, clock, calls) -> None:
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock)
    state = hass.states.get(PUMP_SENSOR)
    assert state.state == "off" and state.attributes["wanted"] is False
    assert state.attributes["controlled"] is False
    await _tick(hass, house, clock, 181)
    assert hass.states.get(PUMP_SENSOR).attributes["wanted"] is True
    assert hass.states.get(PUMP_SENSOR).state == "off"
    assert calls == []


async def test_pump_starts_after_the_delay_and_runs_on(hass, house, clock, calls) -> None:
    await _control(hass, True)
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock)
    assert calls == []
    await _tick(hass, house, clock, 181)
    assert ("turn_on", PUMP) in calls and hass.states.get(PUMP_SENSOR).state == "on"
    set_thermostat(hass, ZONE, "idle")
    await _tick(hass, house, clock, 60)
    assert hass.states.get(PUMP_SENSOR).state == "on"  # run-on
    await _tick(hass, house, clock, 200)
    assert ("turn_off", PUMP) in calls and hass.states.get(PUMP_SENSOR).state == "off"


async def test_unconfirmed_command_is_repeated_and_reported_once(hass, house, clock) -> None:
    hass.services.async_remove("switch", "turn_on")
    sent: list[str] = []

    async def deaf(call: ServiceCall) -> None:
        sent.append(call.data["entity_id"])

    hass.services.async_register("switch", "turn_on", deaf)
    events: list[Any] = []
    hass.bus.async_listen(EVENT_ACTIVITY, events.append)
    await _control(hass, True)
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock, 181)
    for _ in range(6):
        await _tick(hass, house, clock, 11)
    assert sent.count(PUMP) == 3
    failures = [
        e
        for e in events
        if "nepotvrden" in e.data["message"] or "not confirmed" in e.data["message"]
    ]
    assert len(failures) == 1
    await _tick(hass, house, clock, 400)
    assert sent.count(PUMP) == 4  # tried again after a long time


async def test_pause_between_heating_and_cooling_holds_the_pump(hass, house, clock, calls) -> None:
    await _control(hass, True)
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock, 200)
    assert hass.states.get(PUMP_SENSOR).state == "on"
    hass.states.async_set(HEAT_PUMP, "off")
    await hass.async_block_till_done()
    await _tick(hass, house, clock, 10)
    hass.states.async_set(HEAT_PUMP, "cool")
    hass.states.async_set(ZONE, "cool", {"hvac_action": "cooling", "current_temperature": 25})
    await _tick(hass, house, clock, 10)
    circuit = next(iter(house.circuits.values()))
    assert circuit.blocked is not None and circuit.blocked.block == "pause"
    await _tick(hass, house, clock, 3700)
    assert circuit.blocked is None or circuit.blocked.block != "pause"


async def test_mixer_position_follows_the_relays(hass, house, clock) -> None:
    circuit = next(iter(house.circuits.values()))
    circuit.mixer.tracker.set(0.0)
    hass.states.async_set(OPEN, "on")  # somebody else opens it (dry run)
    await hass.async_block_till_done()
    clock.now += 25
    hass.states.async_set(OPEN, "off")
    await hass.async_block_till_done()
    assert float(hass.states.get(POSITION).state) == pytest.approx(25.0)
    hass.states.async_set(CLOSE, "on")
    await hass.async_block_till_done()
    clock.now += 10
    hass.states.async_set(CLOSE, "off")
    await hass.async_block_till_done()
    assert float(hass.states.get(POSITION).state) == pytest.approx(15.0)


async def test_dry_run_proposes_a_mixer_move_without_switching(hass, house, clock, calls) -> None:
    circuit = next(iter(house.circuits.values()))
    circuit.mixer.tracker.set(20.0)
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock)
    circuit.mixer._tick(None)
    assert circuit.mixer.proposal is not None
    assert circuit.mixer.proposal.direction == "open"
    assert calls == []


async def test_live_mixer_homes_unknown_position_then_regulates(hass, house, clock, calls) -> None:
    circuit = next(iter(house.circuits.values()))
    mixer = circuit.mixer
    mixer.tracker.clear()
    await _control(hass, True)
    mixer._tick(None)
    assert calls == []  # not before the homing delay after the start
    clock.now += 31
    mixer._tick(None)
    await hass.async_block_till_done()
    assert ("turn_on", CLOSE) in calls
    assert hass.states.get(POSITION).attributes["movement"] == "homing"
    assert hass.states.get("sensor.f1_mixer_state").state == "homing"
    clock.now += 102
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=105))  # travel + pulse
    await hass.async_block_till_done()
    assert ("turn_off", CLOSE) in calls
    assert mixer.position() == 0.0
    await hass.async_block_till_done()
    assert hass.states.get(POSITION).attributes["movement"] == "idle"


async def test_mixer_never_runs_both_directions(hass, house, clock, calls) -> None:
    await _control(hass, True)
    hass.states.async_set(OPEN, "on")
    await hass.async_block_till_done()
    hass.states.async_set(CLOSE, "on")
    await hass.async_block_till_done()
    assert ("turn_off", OPEN) in calls and ("turn_off", CLOSE) in calls


async def test_relay_on_without_command_is_switched_off(hass, house, clock, calls) -> None:
    circuit = next(iter(house.circuits.values()))
    hass.states.async_set(OPEN, "on")
    await hass.async_block_till_done()
    await _control(hass, True)
    circuit.mixer.tracker.clear()
    circuit.mixer._tick(None)
    await hass.async_block_till_done()
    assert ("turn_off", OPEN) in calls


async def test_condensation_blocks_cooling_pump(hass, house, clock, calls) -> None:
    hass.states.async_set(HEAT_PUMP, "cool")
    circuit = next(iter(house.circuits.values()))
    await _tick(hass, house, clock)
    hass.states.async_set(ZONE, "cool", {"hvac_action": "cooling", "current_temperature": 25})
    house.pause_remaining = 0
    await _tick(hass, house, clock, 3700)
    assert circuit.blocked is not None and circuit.blocked.block == "no_humidity"
    await _control(hass, True)
    await _tick(hass, house, clock, 400)
    assert ("turn_on", PUMP) not in calls


async def test_circuit_switch_keeps_one_circuit_in_dry_run(hass, house, clock, calls) -> None:
    await _control(hass, True, circuits=False)
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock, 200)
    assert hass.states.get(PUMP_SENSOR).attributes["wanted"] is True
    assert hass.states.get(PUMP_SENSOR).attributes["controlled"] is False
    assert calls == []
    next(iter(house.circuits.values())).set_enabled(True)
    await _tick(hass, house, clock)
    assert ("turn_on", PUMP) in calls


async def test_dry_run_takes_the_position_of_the_old_cover_when_it_appears(
    hass, house, clock
) -> None:
    circuit = next(iter(house.circuits.values()))
    circuit.mixer.tracker.clear()
    circuit.mixer.circuit.settings = circuit.settings.__class__(
        **{
            **{f: getattr(circuit.settings, f) for f in circuit.settings.__slots__},
            "mixer_position": "cover.old",
        }
    )
    hass.states.async_set("cover.old", "open", {"current_position": 40})
    circuit.mixer._tick(None)
    assert circuit.mixer.position() == 40


async def test_relay_blip_while_idle_keeps_the_position(hass, house, clock) -> None:
    circuit = next(iter(house.circuits.values()))
    circuit.mixer.tracker.set(40.0)
    for relay in (OPEN, CLOSE):
        hass.states.async_set(relay, "unavailable")
        await hass.async_block_till_done()
        hass.states.async_set(relay, "off")
        await hass.async_block_till_done()
    assert circuit.mixer.position() == 40.0


async def test_idle_blip_is_not_a_move(hass, house, clock) -> None:
    circuit = next(iter(house.circuits.values()))
    circuit.mixer.tracker.set(40.0)
    stored = house.persisted["mixers"].setdefault(circuit.id, {})
    stored["last_move"] = 123.0
    hass.states.async_set(OPEN, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(OPEN, "off")
    await hass.async_block_till_done()
    assert stored["last_move"] == 123.0  # else the exercise after days of rest never comes


async def test_short_blip_while_moving_keeps_counting(hass, house, clock) -> None:
    circuit = next(iter(house.circuits.values()))
    circuit.mixer.tracker.set(40.0)
    hass.states.async_set(OPEN, "on")
    await hass.async_block_till_done()
    clock.now += 5
    hass.states.async_set(OPEN, "unavailable")
    await hass.async_block_till_done()
    clock.now += 0.3
    hass.states.async_set(OPEN, "on")  # the relay ran on through the blip
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    clock.now += 14.7
    hass.states.async_set(OPEN, "off")
    await hass.async_block_till_done()
    assert circuit.mixer.position() == pytest.approx(60.0)


async def test_relay_back_off_after_a_blip_ends_the_move(hass, house, clock) -> None:
    circuit = next(iter(house.circuits.values()))
    circuit.mixer.tracker.set(40.0)
    hass.states.async_set(OPEN, "on")
    await hass.async_block_till_done()
    clock.now += 10
    hass.states.async_set(OPEN, "unavailable")
    await hass.async_block_till_done()
    clock.now += 0.5
    hass.states.async_set(OPEN, "off")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    assert circuit.mixer.position() == pytest.approx(50.5)
    assert not circuit.mixer.tracker.moving


async def test_relay_lost_while_moving_loses_the_position(hass, house, clock) -> None:
    circuit = next(iter(house.circuits.values()))
    circuit.mixer.tracker.set(40.0)
    hass.states.async_set(OPEN, "on")
    await hass.async_block_till_done()
    hass.states.async_set(OPEN, "unavailable")
    await hass.async_block_till_done()
    assert circuit.mixer.position() is not None  # a moment may be a blip
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert circuit.mixer.position() is None


async def test_homing_cut_short_is_repeated(hass, house, clock, calls) -> None:
    circuit = next(iter(house.circuits.values()))
    mixer = circuit.mixer
    mixer.tracker.clear()
    await _control(hass, True)
    clock.now += 31
    mixer._tick(None)
    await hass.async_block_till_done()
    assert mixer.status() == "homing"
    clock.now += 10
    hass.states.async_set(CLOSE, "off")  # an old script stops the relay early
    await hass.async_block_till_done()
    assert mixer.position() is None
    assert mixer.status() == "unknown"
    mixer._tick(None)
    await hass.async_block_till_done()
    assert calls.count(("turn_on", CLOSE)) == 2


async def _restart_mixer(hass, house, *, booting: bool, home: bool) -> Any:
    """The mixer as it starts again, with the house start flag and the homing setting."""
    house.persisted["tuning"][house.id]["home_mixers_on_start"] = home
    await _control(hass, True)
    mixer = next(iter(house.circuits.values())).mixer
    mixer.tracker.set(40.0)
    mixer.async_stop()
    house.booting = booting
    mixer.async_start()
    await hass.async_block_till_done()
    return mixer


async def test_mixer_is_homed_when_home_assistant_starts(hass, house, clock, calls) -> None:
    mixer = await _restart_mixer(hass, house, booting=True, home=True)
    assert mixer.position() is None
    clock.now += 31
    mixer._tick(None)
    await hass.async_block_till_done()
    assert ("turn_on", CLOSE) in calls
    assert mixer.status() == "homing"


async def test_saved_position_is_kept_without_the_setting_or_on_a_reload(
    hass, house, clock, calls
) -> None:
    assert (await _restart_mixer(hass, house, booting=True, home=False)).position() == 40.0
    assert (await _restart_mixer(hass, house, booting=False, home=True)).position() == 40.0


async def test_booting_only_while_home_assistant_starts(hass, make_entry) -> None:
    hass.set_state(CoreState.not_running)
    entry = make_entry(circuit_data("F1"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.booting
    hass.set_state(CoreState.running)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert not entry.runtime_data.booting


async def test_pump_sensor_keeps_its_state_through_a_blip(hass, house, clock) -> None:
    await _tick(hass, house, clock)
    assert hass.states.get(PUMP_SENSOR).state == "off"
    hass.states.async_set(PUMP, "unavailable")
    await _tick(hass, house, clock, 0.3)
    assert hass.states.get(PUMP_SENSOR).state == "off"
    await _tick(hass, house, clock, 6)
    assert hass.states.get(PUMP_SENSOR).state == "unknown"


async def test_live_mixer_waits_for_a_move_to_show(hass, house, clock, calls) -> None:
    circuit = next(iter(house.circuits.values()))
    mixer = circuit.mixer
    mixer.tracker.set(50.0)
    await _control(hass, True)
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock)
    mixer._tick(None)
    await hass.async_block_till_done()
    assert calls.count(("turn_on", OPEN)) == 1
    clock.now += 20
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()
    assert ("turn_off", OPEN) in calls
    clock.now += 30
    mixer._tick(None)
    await hass.async_block_till_done()
    assert calls.count(("turn_on", OPEN)) == 1  # the water has not reached the sensor yet
    clock.now += 150
    mixer._tick(None)
    await hass.async_block_till_done()
    assert calls.count(("turn_on", OPEN)) == 2


async def test_running_pump_is_kept_until_the_zones_load(hass, house, clock, calls) -> None:
    hass.states.async_set(PUMP, "on")
    await _control(hass, True)
    await _tick(hass, house, clock, 10)
    assert ("turn_off", PUMP) not in calls  # no demand yet: the zones may still be loading
    await _tick(hass, house, clock, 90)
    assert ("turn_off", PUMP) in calls


async def test_mixer_is_not_closed_until_the_zones_load(hass, house, clock, calls) -> None:
    mixer = next(iter(house.circuits.values())).mixer
    mixer.tracker.set(40.0)
    await _control(hass, True)
    clock.now += 31
    mixer._tick(None)
    await hass.async_block_till_done()
    assert ("turn_on", CLOSE) not in calls
    clock.now += 60
    mixer._tick(None)
    await hass.async_block_till_done()
    assert ("turn_on", CLOSE) in calls


async def test_mixer_follows_the_source_at_once(hass, house, clock, calls) -> None:
    mixer = next(iter(house.circuits.values())).mixer
    mixer.tracker.set(40.0)
    await _control(hass, True)
    set_thermostat(hass, ZONE, "heating")
    hass.states.async_set(SUPPLY, "35.0")
    await _tick(hass, house, clock, 100)
    mixer._tick(None)  # sets the source reference
    await hass.async_block_till_done()
    calls.clear()
    hass.states.async_set(SOURCE, "50.0")  # the heat pump starts heating the tank
    await _tick(hass, house, clock, 30)
    mixer._tick(None)
    await hass.async_block_till_done()
    assert ("turn_on", CLOSE) in calls
    assert hass.states.get(POSITION).attributes["source_temperature"] == 50.0


async def test_activity_says_why_the_mixer_moves(hass, house, clock, calls) -> None:
    mixer = next(iter(house.circuits.values())).mixer
    mixer.tracker.set(50.0)
    await _control(hass, True)
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock, 100)
    events = async_capture_events(hass, EVENT_ACTIVITY)
    mixer._tick(None)
    await hass.async_block_till_done()
    moves = [e.data["message"] for e in events if "Mixer F1" in e.data["message"]]
    assert moves and "below the target" in moves[0]


async def test_activity_reports_a_source_that_is_not_enough(hass, house, clock, calls) -> None:
    mixer = next(iter(house.circuits.values())).mixer
    mixer.tracker.set(100.0)
    await _control(hass, True)
    set_thermostat(hass, ZONE, "heating")
    hass.states.async_set(SUPPLY, "20.0")  # far below any target, tank warm
    hass.states.async_set(SOURCE, "60.0")
    await _tick(hass, house, clock, 100)
    events = async_capture_events(hass, EVENT_ACTIVITY)
    mixer._tick(None)  # an end-stop pulse first
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    clock.now += 901
    mixer._tick(None)
    await hass.async_block_till_done()
    assert any("not enough" in e.data["message"] for e in events)
    assert hass.states.get(POSITION).attributes["source_not_enough"] is True
    assert hass.states.get("binary_sensor.f1_source_not_enough").state == "on"


async def test_a_start_reported_after_the_stop_is_switched_off(hass, house, clock, calls) -> None:
    """The board drops off just as a move starts; its "on" comes after the move ended."""
    mixer = next(iter(house.circuits.values())).mixer
    mixer.tracker.set(50.0)
    await _control(hass, True)
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock, 100)
    hass.services.async_remove("switch", "turn_on")  # the command is lost in the blip for now
    turned_on: list[str] = []

    async def late_on(call):
        turned_on.append(call.data["entity_id"])

    hass.services.async_register("switch", "turn_on", late_on)
    mixer._tick(None)
    await hass.async_block_till_done()
    assert turned_on == [OPEN]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=21))  # the 20 s move ends
    await hass.async_block_till_done()
    assert ("turn_off", OPEN) in calls  # the stop is sent although the state still says off
    calls.clear()
    hass.states.async_set(OPEN, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(OPEN, "on")  # the late start arrives with the board
    await hass.async_block_till_done()
    assert ("turn_off", OPEN) in calls  # stopped at once, not after the full travel


async def test_unavailable_relay_stops_the_mixer_and_is_reported(hass, house, clock, calls) -> None:
    mixer = next(iter(house.circuits.values())).mixer
    mixer.tracker.set(50.0)
    await _control(hass, True)
    set_thermostat(hass, ZONE, "heating")
    await _tick(hass, house, clock, 100)
    events = async_capture_events(hass, EVENT_ACTIVITY)
    hass.states.async_set(OPEN, "unavailable")
    await hass.async_block_till_done()
    mixer._tick(None)  # a blip: not yet
    assert not any("unavailable" in e.data["message"] for e in events)
    clock.now += 6
    calls.clear()
    mixer._tick(None)
    await hass.async_block_till_done()
    assert calls == []  # supply 30 is below the target, but nothing is moved
    assert any(
        "F1 mixer open" in e.data["message"] and "unavailable" in e.data["message"] for e in events
    )
    assert hass.states.get("sensor.f1_mixer_state").state == "unavailable"
    assert mixer.position() == 50.0  # it stood: the position is kept
    hass.states.async_set(OPEN, "off")
    await hass.async_block_till_done()
    mixer._tick(None)
    await hass.async_block_till_done()
    assert any("available again" in e.data["message"] for e in events)
    assert ("turn_on", OPEN) in calls  # regulates again


async def test_move_lost_with_the_relay_is_reported(hass, house, clock) -> None:
    circuit = next(iter(house.circuits.values()))
    circuit.mixer.tracker.set(40.0)
    events = async_capture_events(hass, EVENT_ACTIVITY)
    hass.states.async_set(OPEN, "on")
    await hass.async_block_till_done()
    hass.states.async_set(OPEN, "unavailable")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert any("position unknown" in e.data["message"] for e in events)


async def test_unavailable_pump_relay_is_reported(hass, house, clock, calls) -> None:
    events = async_capture_events(hass, EVENT_ACTIVITY)
    hass.states.async_set(PUMP, "unavailable")
    await _tick(hass, house, clock)
    await _tick(hass, house, clock, 6)
    assert any(
        "F1 pump" in e.data["message"] and "unavailable" in e.data["message"] for e in events
    )


async def test_mode_sensor_tells_the_schema_card_its_entities(hass, house) -> None:
    layout = hass.states.get("sensor.climate_circuits_mode").attributes["layout"]
    assert layout["control"] == "switch.climate_circuits_control_equipment"
    (circuit,) = layout["circuits"]
    assert circuit["name"] == "F1"
    assert circuit["pump"] == PUMP_SENSOR
    assert circuit["mixer"] == POSITION
    assert circuit["mixer_state"] == "sensor.f1_mixer_state"
    assert circuit["target"] == "sensor.f1_target_water_temperature"
    assert circuit["supply"] == SUPPLY
    assert layout["hot_water"] is None


async def test_relay_board_connecting_at_start_is_not_a_drop_out(hass, house, clock) -> None:
    events = async_capture_events(hass, EVENT_ACTIVITY)
    mixer = next(iter(house.circuits.values())).mixer
    mixer.close._known = None  # never seen since the start
    hass.states.async_set(CLOSE, "unavailable")
    await _tick(hass, house, clock, 30)
    mixer._tick(None)
    assert not any("unavailable" in e.data["message"] for e in events)
    await _tick(hass, house, clock, 61)  # past the start grace
    mixer._tick(None)
    await hass.async_block_till_done()
    assert any("unavailable" in e.data["message"] for e in events)


async def test_regulation_values_are_numbers_on_the_circuit(hass, house, clock) -> None:
    circuit = next(iter(house.circuits.values()))
    # What the circuit's configuration held before is kept: travel 100 s, pump delay 180 s.
    assert hass.states.get("number.f1_mixer_travel_time").state == "100.0"
    assert hass.states.get("number.f1_pump_start_delay").state == "180.0"
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.f1_mixer_settle_time", "value": 240},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.f1_pump_start_delay", "value": 60},
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.f1_mixer_follows_the_heat_source"},
        blocking=True,
    )
    assert circuit.mixer.params.settle == 240
    assert circuit.mixer.params.compensate is False
    assert circuit.pump.timer.delay == 60
    relay = hass.states.get("sensor.f1_mixer_open_relay")
    assert relay.attributes["entity_id"] == OPEN and relay.state == "f1 open"
    assert hass.states.get("sensor.f1_pump_relay").attributes["entity_id"] == PUMP
    assert hass.states.get("sensor.f1_heating_thermostats").attributes["entity_id"] == ZONE
    assert hass.states.get("sensor.f1_cooling_thermostats") is None  # none linked


async def test_end_pulse_time_outlives_a_restart(hass, house, clock) -> None:
    mixer = next(iter(house.circuits.values())).mixer
    mixer._last_end_pulse = clock.now - 600
    mixer._persist()
    mixer._last_end_pulse = None
    clock.now += 100  # monotonic time starts anew after a restart, wall time goes on
    clock.wall += 100
    mixer._seed()
    assert mixer._last_end_pulse == pytest.approx(clock.now - 700)
