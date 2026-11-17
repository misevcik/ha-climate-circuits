"""Hot water circulation pump: entities, hysteresis, control and Activity."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.climate_circuits.const import EVENT_ACTIVITY

from .conftest import HEAT_PUMP, HOUSE_OPTIONS

SENSOR = "sensor.circulation_return"
PUMP = "switch.circulation_pump"
STATE = "sensor.hot_water_circulation_state"
THRESHOLD = "number.hot_water_circulation_threshold"
DELTA = "number.hot_water_circulation_delta"
ENABLED = "switch.hot_water_circulation_enabled"
OPTIONS: dict[str, Any] = {
    **HOUSE_OPTIONS,
    "hot_water": {
        "circulation_sensor": SENSOR,
        "circulation_pump": PUMP,
        "threshold": 37.0,
        "delta": 1.0,
    },
}


@pytest.fixture
async def entry(hass: HomeAssistant, make_entry):
    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(SENSOR, "36.5")
    hass.states.async_set(PUMP, "off")
    entry = make_entry(options=OPTIONS)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _temperature(hass: HomeAssistant, value: str) -> None:
    hass.states.async_set(SENSOR, value)
    await hass.async_block_till_done()


async def test_entities_on_hot_water_device(hass: HomeAssistant, entry) -> None:
    assert hass.states.get(STATE).state == "stopped"
    assert float(hass.states.get(THRESHOLD).state) == 37.0
    assert float(hass.states.get(DELTA).state) == 1.0
    assert hass.states.get(ENABLED).state == "on"
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("climate_circuits", f"{entry.entry_id}_hot_water"), entry.entry_id
    )
    assert device is not None and device.name == "Hot water"


async def test_no_hot_water_without_config(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(HEAT_PUMP, "heat")
    entry = make_entry()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(STATE) is None
    assert hass.states.get(THRESHOLD) is None


async def test_circulation_temperature_sensor(hass: HomeAssistant, entry) -> None:
    temperature = "sensor.hot_water_circulation_temperature"
    assert float(hass.states.get(temperature).state) == 36.5
    await _temperature(hass, "35.2")
    assert float(hass.states.get(temperature).state) == 35.2
    entry.runtime_data.started -= 100  # past the start grace
    await _temperature(hass, "unavailable")
    assert hass.states.get(temperature).state == "unknown"


async def test_hysteresis_follows_the_real_pump(hass: HomeAssistant, entry) -> None:
    """In dry run somebody else drives the pump; the sensor shows what it would do beside it."""
    calls = async_mock_service(hass, "switch", "turn_on")
    await _temperature(hass, "35.9")
    assert hass.states.get(STATE).state == "running"
    hass.states.async_set(PUMP, "on")  # the pump follows (another automation)
    await _temperature(hass, "36.5")
    assert hass.states.get(STATE).state == "running"
    await _temperature(hass, "37.0")
    assert hass.states.get(STATE).state == "stopped"
    hass.states.async_set(PUMP, "off")
    await _temperature(hass, "36.5")
    assert hass.states.get(STATE).state == "stopped"
    attributes = hass.states.get(STATE).attributes
    assert attributes["starts_below"] == 36.0 and attributes["stops_at"] == 37.0
    assert attributes["controlled"] is False
    assert not calls  # dry run: the pump is never switched


async def test_pump_stopped_by_someone_else_is_not_running(hass: HomeAssistant, entry) -> None:
    await _temperature(hass, "35.9")
    hass.states.async_set(PUMP, "on")
    await _temperature(hass, "36.0")
    assert hass.states.get(STATE).state == "running"
    hass.states.async_set(PUMP, "off")  # the old automation stops it at 36.0
    await hass.async_block_till_done()
    assert hass.states.get(STATE).state == "stopped"


async def test_switches_pump_when_controlling(hass: HomeAssistant, entry) -> None:
    on = async_mock_service(hass, "switch", "turn_on")
    off = async_mock_service(hass, "switch", "turn_off")
    entry.runtime_data.set_control_equipment(True)
    await _temperature(hass, "35.0")
    assert [c.data["entity_id"] for c in on] == [PUMP]
    hass.states.async_set(PUMP, "on")
    await _temperature(hass, "37.5")
    assert [c.data["entity_id"] for c in off] == [PUMP]


async def test_disable_switch_stops_pump(hass: HomeAssistant, entry) -> None:
    await _temperature(hass, "30.0")
    await hass.services.async_call("switch", "turn_off", {"entity_id": ENABLED}, blocking=True)
    assert hass.states.get(STATE).state == "disabled"


async def test_unavailable_sensor(hass: HomeAssistant, entry) -> None:
    entry.runtime_data.started -= 100  # past the start grace
    await _temperature(hass, "unavailable")
    assert hass.states.get(STATE).state == "unavailable"


async def test_unavailable_sensor_is_tolerated_right_after_the_start(
    hass: HomeAssistant, entry
) -> None:
    events = []
    hass.bus.async_listen(EVENT_ACTIVITY, events.append)
    await _temperature(hass, "unavailable")
    assert hass.states.get(STATE).state != "unavailable"
    assert not events


async def test_threshold_change_without_reload(hass: HomeAssistant, entry) -> None:
    events = []
    hass.bus.async_listen(EVENT_ACTIVITY, events.append)
    with patch.object(hass.config_entries, "async_reload") as reload:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": THRESHOLD, "value": 40.0}, blocking=True
        )
        await hass.async_block_till_done()
    reload.assert_not_called()
    assert entry.runtime_data.persisted["tuning"][f"{entry.entry_id}_hot_water"] == {
        "circulation_threshold": 40.0,
        "circulation_delta": 1.0,
        "circulation_max_run": 10,
        "circulation_pause": 30,
    }
    assert hass.states.get(STATE).attributes["stops_at"] == 40.0
    # 36.5 °C is now below 40 − 1: the pump starts.
    assert hass.states.get(STATE).state == "running"
    messages = [e.data["message"] for e in events]
    assert any(m.startswith("On – circulation 36.5 °C is below 39.0 °C") for m in messages)


async def test_other_option_change_reloads(hass: HomeAssistant, entry) -> None:
    with patch.object(hass.config_entries, "async_reload") as reload:
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "hot_water": {**entry.options["hot_water"], "circulation_pump": "switch.other"},
            },
        )
        await hass.async_block_till_done()
    reload.assert_called_once()


async def test_schema_card_gets_the_hot_water_entities(hass: HomeAssistant, entry) -> None:
    hw = hass.states.get("sensor.climate_circuits_mode").attributes["layout"]["hot_water"]
    assert hw["state"] == STATE
    assert hw["threshold"] == THRESHOLD and hw["delta"] == DELTA and hw["enabled"] == ENABLED
    assert hw["temperature"] == "sensor.hot_water_circulation_temperature"
    assert hw["tank"] is None


TANK = "sensor.hot_water_tank"
SCHEDULE = "schedule.circulation"
MAX_RUN = "number.hot_water_circulation_longest_run"
PAUSE = "number.hot_water_circulation_pause"
MARGIN = "number.hot_water_circulation_below_the_tank"


async def _setup(hass: HomeAssistant, make_entry, **hot_water: Any):
    hass.states.async_set(HEAT_PUMP, "heat")
    hass.states.async_set(SENSOR, "36.5")
    hass.states.async_set(PUMP, "off")
    options = {**OPTIONS, "hot_water": {**OPTIONS["hot_water"], **hot_water}}
    entry = make_entry(options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


class _Clock:
    def __init__(self, house) -> None:
        self.now = time.time()  # near the real clock: a reloaded house reads the real one
        house.now = lambda: self.now
        house.wall = lambda: self.now
        house.started = self.now - 100


async def _tick(hass: HomeAssistant, entry) -> None:
    entry.runtime_data.evaluate()
    await hass.async_block_till_done()


async def test_longest_run_and_pause_entities(hass: HomeAssistant, entry) -> None:
    assert float(hass.states.get(MAX_RUN).state) == 10
    assert float(hass.states.get(PAUSE).state) == 30
    assert hass.states.get(MARGIN) is None  # only with a tank sensor


async def test_a_run_that_does_not_warm_up_pauses(hass: HomeAssistant, entry) -> None:
    on = async_mock_service(hass, "switch", "turn_on")
    off = async_mock_service(hass, "switch", "turn_off")
    clock = _Clock(entry.runtime_data)
    entry.runtime_data.set_control_equipment(True)
    await _temperature(hass, "34.0")
    assert [c.data["entity_id"] for c in on] == [PUMP]
    hass.states.async_set(PUMP, "on")
    await hass.async_block_till_done()
    clock.now += 9 * 60
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "running"
    clock.now += 61
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "paused"
    assert hass.states.get(STATE).attributes["paused_until"] == dt_util.utc_from_timestamp(
        clock.now + 30 * 60
    )
    assert [c.data["entity_id"] for c in off] == [PUMP]
    hass.states.async_set(PUMP, "off")
    await hass.async_block_till_done()
    clock.now += 29 * 60
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "paused"
    assert len(on) == 1
    clock.now += 61
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "running"
    assert len(on) == 2


async def test_pause_is_reported_once(hass: HomeAssistant, entry) -> None:
    events = []
    hass.bus.async_listen(EVENT_ACTIVITY, events.append)
    clock = _Clock(entry.runtime_data)
    hass.states.async_set(PUMP, "on")
    await _temperature(hass, "34.0")
    clock.now += 11 * 60
    await _tick(hass, entry)
    await _tick(hass, entry)
    paused = [e for e in events if e.data["message"].startswith("Paused")]
    assert len(paused) == 1
    assert (
        paused[0]
        .data["message"]
        .startswith("Paused – circulation 34.0 °C did not reach 37.0 °C in 10 min, again at ")
    )
    until = dt_util.as_local(dt_util.utc_from_timestamp(clock.now + 30 * 60)).strftime("%H:%M")
    assert until in paused[0].data["message"]


async def test_the_tank_lowers_where_the_circulation_stops(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(TANK, "39.0")
    entry = await _setup(hass, make_entry, tank_sensor=TANK)
    assert float(hass.states.get(MARGIN).state) == 5
    attributes = hass.states.get(STATE).attributes
    assert attributes["stops_at"] == 34.0 and attributes["stop_from_tank"] is True
    assert hass.states.get(STATE).state == "stopped"  # 36.5 °C is above 39 − 5
    assert "(from the hot water tank)" in attributes["reason"]
    hass.states.async_set(TANK, "50.0")
    await _tick(hass, entry)  # the tank is read on the regular evaluation
    assert hass.states.get(STATE).attributes["stops_at"] == 37.0
    assert entry.runtime_data.hot_water.decision.tank_limited is False


async def test_outside_the_schedule_the_pump_stays_off(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(SCHEDULE, "off")
    entry = await _setup(hass, make_entry, circulation_schedule=SCHEDULE)
    off = async_mock_service(hass, "switch", "turn_off")
    on = async_mock_service(hass, "switch", "turn_on")
    entry.runtime_data.set_control_equipment(True)
    await _temperature(hass, "30.0")
    assert hass.states.get(STATE).state == "outside_schedule"
    assert not on
    hass.states.async_set(SCHEDULE, "on")
    await hass.async_block_till_done()
    assert hass.states.get(STATE).state == "running"
    assert [c.data["entity_id"] for c in on] == [PUMP]
    hass.states.async_set(PUMP, "on")
    hass.states.async_set(SCHEDULE, "off")
    await hass.async_block_till_done()
    assert [c.data["entity_id"] for c in off][-1] == PUMP
    assert hass.states.get("sensor.hot_water_circulation_schedule").state is not None


async def test_a_missing_schedule_does_not_stop_the_circulation(
    hass: HomeAssistant, make_entry
) -> None:
    await _setup(hass, make_entry, circulation_schedule=SCHEDULE)
    await _temperature(hass, "30.0")
    assert hass.states.get(STATE).state == "running"


async def test_a_changed_limit_applies_to_a_running_pause(hass: HomeAssistant, entry) -> None:
    clock = _Clock(entry.runtime_data)
    hass.states.async_set(PUMP, "on")
    await _temperature(hass, "34.0")
    clock.now += 11 * 60
    await _tick(hass, entry)
    hass.states.async_set(PUMP, "off")
    await hass.async_block_till_done()
    assert hass.states.get(STATE).state == "paused"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": PAUSE, "value": 5}, blocking=True
    )
    paused_at = entry.runtime_data.hot_water.paused_at
    assert hass.states.get(STATE).attributes["paused_until"] == dt_util.utc_from_timestamp(
        paused_at + 5 * 60
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": MAX_RUN, "value": 0}, blocking=True
    )
    assert hass.states.get(STATE).state == "running"


async def test_a_pause_outlasts_a_reload(hass: HomeAssistant, entry) -> None:
    clock = _Clock(entry.runtime_data)
    clock.now -= 12 * 60  # the reloaded house reads the real clock: the pause began in the past
    hass.states.async_set(PUMP, "on")
    await _temperature(hass, "34.0")
    clock.now += 11 * 60
    await _tick(hass, entry)
    hass.states.async_set(PUMP, "off")
    await hass.async_block_till_done()
    paused_at = entry.runtime_data.hot_water.paused_at
    assert paused_at == clock.now
    await entry.runtime_data._store.async_save(entry.runtime_data._data())
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.hot_water.paused_at == paused_at
    assert hass.states.get(STATE).state == "paused"


async def test_the_tank_margin_goes_with_the_tank_sensor(hass: HomeAssistant, make_entry) -> None:
    hass.states.async_set(TANK, "39.0")
    entry = await _setup(hass, make_entry, tank_sensor=TANK)
    assert hass.states.get(MARGIN) is not None
    hot_water = {k: v for k, v in entry.options["hot_water"].items() if k != "tank_sensor"}
    hass.config_entries.async_update_entry(entry, options={**entry.options, "hot_water": hot_water})
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get(MARGIN) is None


async def test_switching_off_does_not_cut_a_pause_short(hass: HomeAssistant, entry) -> None:
    clock = _Clock(entry.runtime_data)
    hass.states.async_set(PUMP, "on")
    await _temperature(hass, "34.0")
    clock.now += 11 * 60
    await _tick(hass, entry)
    hass.states.async_set(PUMP, "off")
    await hass.async_block_till_done()
    await hass.services.async_call("switch", "turn_off", {"entity_id": ENABLED}, blocking=True)
    assert hass.states.get(STATE).state == "disabled"
    clock.now += 60
    await hass.services.async_call("switch", "turn_on", {"entity_id": ENABLED}, blocking=True)
    assert hass.states.get(STATE).state == "paused"
    assert hass.states.get(STATE).attributes["paused_until"] == dt_util.utc_from_timestamp(
        clock.now - 60 + 30 * 60
    )


async def test_a_relay_blip_does_not_restart_the_run(hass: HomeAssistant, entry) -> None:
    clock = _Clock(entry.runtime_data)
    hass.states.async_set(PUMP, "on")
    await _temperature(hass, "34.0")
    clock.now += 9 * 60
    hass.states.async_set(PUMP, "unavailable")
    await _tick(hass, entry)
    hass.states.async_set(PUMP, "on")
    clock.now += 2 * 60
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "paused"


async def test_a_pause_stored_ahead_of_the_clock_lasts_one_pause(
    hass: HomeAssistant, entry
) -> None:
    clock = _Clock(entry.runtime_data)
    hot_water = entry.runtime_data.hot_water
    hot_water.paused_at = clock.now + 5 * 3600  # saved while the clock was hours ahead
    await _tick(hass, entry)
    assert hot_water.paused_at == clock.now
    assert hass.states.get(STATE).state == "paused"
    clock.now += 30 * 60 + 1
    await _tick(hass, entry)
    assert hass.states.get(STATE).state != "paused"


async def test_taking_control_restarts_the_run(hass: HomeAssistant, entry) -> None:
    clock = _Clock(entry.runtime_data)
    hass.states.async_set(PUMP, "on")  # driven by somebody else during the dry run
    await _temperature(hass, "36.5")
    clock.now += 9 * 60
    await _tick(hass, entry)
    entry.runtime_data.set_control_equipment(True)
    await hass.async_block_till_done()
    clock.now += 2 * 60  # 11 min on, but only 2 of them under control
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "running"
    clock.now += 9 * 60
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "paused"


async def test_a_pump_that_never_stops_runs_afresh_after_a_pause(
    hass: HomeAssistant, entry
) -> None:
    clock = _Clock(entry.runtime_data)
    hass.states.async_set(PUMP, "on")  # dry run: somebody else keeps it running
    await _temperature(hass, "34.0")
    clock.now += 11 * 60
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "paused"
    clock.now += 30 * 60 + 1
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "running"
    clock.now += 9 * 60
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "running"
    clock.now += 2 * 60
    await _tick(hass, entry)
    assert hass.states.get(STATE).state == "paused"
