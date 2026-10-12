"""Runtime of one house: reads entities, decides, notifies entities, writes Activity.

Outputs act only while control_equipment is on (circuit pumps and mixers also need the
circuit's own switch); otherwise the decision is a dry run shown in Activity.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store

from .activity import entity_id_for, log_activity
from .const import (
    CURVE_SECTIONS,
    DEW_POINT_MARGIN,
    EVALUATE_INTERVAL,
    HOT_WATER_GRACE,
    HOT_WATER_TUNING,
    STORAGE_KEY,
    STORAGE_VERSION,
    ZONE_COMMAND_ATTEMPTS,
    ZONE_COMMAND_RETRY,
)
from .core.circulation import CirculationDecision, CirculationReason, circulation_decision
from .core.curve import WaterTarget, water_target, worst_dew_point
from .core.demand import Demand, circuit_demand
from .core.explain import CircuitExplanation, ZoneSnapshot, explain_circuit
from .core.mode import Mode, ModeDecision, ModeSource, Override, mode_from_entity, resolve_mode
from .core.protect import Block, Blocked, CondensationGuard, ModePause
from .core.texts import (
    circuit_reason,
    circulation_message,
    mode_message,
    other_zones_kind,
    zones_message,
)
from .core.zones import OFF, ZonePlan, plan_zones
from .outputs import MixerController, PumpController, Relay
from .settings import CircuitSettings, HotWaterSettings, HouseSettings
from .states import call_service, float_of, name_of, number, state_of


def _describe(hass: HomeAssistant, entity_id: str) -> str | None:
    """E.g. "45.0 °C"."""
    if (state := hass.states.get(entity_id)) is None:
        return None
    if (value := number(state.state)) is None:
        return state.state
    unit = state.attributes.get("unit_of_measurement")
    return f"{value:.1f} {unit}" if unit else f"{value:.1f}"


def _zone_snapshot(hass: HomeAssistant, entity_id: str) -> ZoneSnapshot:
    if (state := state_of(hass, entity_id)) is None:
        return ZoneSnapshot(entity_id, name_of(hass, entity_id) or entity_id, available=False)
    attributes = state.attributes
    return ZoneSnapshot(
        entity_id,
        state.name,
        available=True,
        hvac_mode=state.state,
        hvac_action=attributes.get("hvac_action"),
        current=number(attributes.get("current_temperature")),
        target=number(attributes.get("temperature")),
    )


class Listeners:
    def __init__(self) -> None:
        self._listeners: list[Callable[[], None]] = []

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()


class Circuit(Listeners):
    def __init__(self, house: House, subentry: ConfigSubentry) -> None:
        super().__init__()
        self.house = house
        self.id = subentry.subentry_id
        self.settings = CircuitSettings.from_data(subentry.data)
        self.demand = Demand(False, reason="not evaluated")
        self.target: WaterTarget | None = None
        self.dew_point: float | None = None
        self.explanation: CircuitExplanation | None = None
        self.blocked: Blocked | None = None
        self.guard = CondensationGuard()
        self.pump = PumpController(self) if self.settings.pump else None
        self.mixer = (
            MixerController(self)
            if self.settings.mixer_open and self.settings.mixer_close
            else None
        )
        self._logged: tuple[Any, ...] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.house.persisted["circuits"].get(self.id, {}).get("enabled", False))

    @property
    def controlling(self) -> bool:
        """Pump and mixer are switched only with the house switch and the circuit's own on."""
        return self.house.control_equipment and self.enabled

    @callback
    def set_enabled(self, enabled: bool) -> None:
        self.house.persisted["circuits"].setdefault(self.id, {})["enabled"] = enabled
        self.house.save()
        self.house.evaluate()

    @property
    def output_demand(self) -> bool:
        """Demand the pump and the mixer follow: not while a protection holds them back."""
        return self.demand.active and self.blocked is None

    @property
    def name(self) -> str:
        return self.settings.name

    def inputs(self) -> set[str]:
        s = self.settings
        return {
            *s.zones,
            *s.humidity_sensors,
            *filter(None, [s.supply_sensor, s.source_sensor, s.mixer_position]),
            *(self.pump.inputs() if self.pump else ()),
            *(self.mixer.inputs() if self.mixer else ()),
        }

    def mixer_position(self) -> float | None:
        """Position in %: tracked by the mixer controller, else read from the old cover."""
        if self.mixer:
            return self.mixer.position()
        state = state_of(self.house.hass, self.settings.mixer_position)
        return number(state.attributes.get("current_position")) if state else None

    @callback
    def async_start(self) -> None:
        if self.mixer:
            self.mixer.async_start()

    @callback
    def async_stop(self) -> None:
        if self.mixer:
            self.mixer.async_stop()

    @callback
    def refresh(self) -> None:
        self._notify()

    def supply_temperature(self) -> float | None:
        return float_of(self.house.hass, self.settings.supply_sensor)

    def source_temperature(self) -> float | None:
        """Water coming to the mixer (buffer tank, heat pump), when a sensor is set."""
        return float_of(self.house.hass, self.settings.source_sensor)

    @callback
    def evaluate(self, mode: Mode, outdoor: float | None) -> None:
        hass, s = self.house.hass, self.settings
        snapshots = {zone: _zone_snapshot(hass, zone) for zone in s.zones}
        actions = {z: snap.hvac_action for z, snap in snapshots.items()}
        temperatures = [snap.current for snap in snapshots.values() if snap.current is not None]
        humidities = [h for e in s.humidity_sensors if (h := float_of(hass, e)) is not None]

        self.demand = circuit_demand(mode, s.heating_zones, s.cooling_zones, actions)
        mode_zones = s.cooling_zones if mode is Mode.COOL else s.heating_zones
        self.explanation = explain_circuit(mode, [snapshots[z] for z in mode_zones], self.demand)
        self.dew_point = worst_dew_point(temperatures, humidities)
        curve = s.heat_curve if mode is Mode.HEAT else s.cool_curve
        self.target = water_target(mode, curve, outdoor, self.dew_point, DEW_POINT_MARGIN)
        self.blocked = self._check_protections(mode, self.house.pause_remaining, temperatures)
        self._log_change()
        if self.pump:
            self.pump.evaluate()
        self._notify()

    def _check_protections(
        self, mode: Mode, pause: float, temperatures: list[float]
    ) -> Blocked | None:
        """Why a calling circuit may not run: the pause after the other mode, condensation."""
        if not self.demand.active:
            self.guard = CondensationGuard()
            return None
        if pause > 0:
            return Blocked(Block.PAUSE, pause)
        if mode is Mode.COOL:
            return self.guard.check(self.house.now(), self.supply_temperature(), self.dew_point)
        return None

    @callback
    def _log_change(self) -> None:
        """Activity entry when the state or the calling zones change."""
        e, house = self.explanation, self.house
        if not house.logging or e is None:
            return
        key = (e.state, tuple(z.zone.entity_id for z in e.calling))
        if key != self._logged:
            self._logged = key
            message = circuit_reason(e, house.hass.config.language, house.decision.reason)
            house.activity(self.name, message, f"{self.id}_state")


class HotWater(Listeners):
    def __init__(self, house: House, settings: HotWaterSettings) -> None:
        super().__init__()
        self.house = house
        self.settings = settings
        self.enabled = True
        self.decision: CirculationDecision | None = None
        self._logged: tuple[Any, ...] | None = None
        self.relay = Relay(house, settings.pump, "Hot water circulation pump")

    @property
    def id(self) -> str:
        return f"{self.house.entry.entry_id}_hot_water"

    def inputs(self) -> set[str]:
        return {self.settings.sensor, self.settings.pump}

    def pump_state(self) -> bool | None:
        return (
            state.state == "on"
            if (state := state_of(self.house.hass, self.settings.pump))
            else None
        )

    @callback
    def evaluate(self) -> None:
        s = self.settings
        # The relay is the hysteresis memory, so a dry run mirrors a pump somebody else drives.
        pump = self.pump_state()
        running = pump if pump is not None else bool(self.decision and self.decision.on)
        temperature = float_of(self.house.hass, s.sensor)
        if temperature is None and self.house.now() - self.house.started < HOT_WATER_GRACE:
            return  # sensors of boards that start with Home Assistant are not there yet
        self.decision = circulation_decision(
            temperature, s.threshold, s.delta, running, self.enabled
        )
        self._log_change()
        if self.house.control_equipment and self.decision is not None:
            self.relay.ensure(self.decision.on)
        self._notify()

    @callback
    def _log_change(self) -> None:
        """Activity entry when the pump starts or stops, or cannot run."""
        decision, house = self.decision, self.house
        if not house.logging or decision is None:
            return
        special = decision.reason in (CirculationReason.DISABLED, CirculationReason.NO_SENSOR)
        key = (decision.on, decision.reason if special else None)
        if key != self._logged:
            self._logged = key
            message = circulation_message(
                decision, house.hass.config.language, dry_run=not house.control_equipment
            )
            house.activity("Hot water", message, f"{self.id}_circulation")

    @callback
    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.house.save()
        self.evaluate()


class ZoneSwitcher:
    """Switches thermostat sets on a mode change and keeps the other set off.

    The other mode's thermostats are turned off first; the new ones are switched on only
    once all of those report off (both sets drive the same zone relays). A thermostat of
    the other mode that comes on later (a schedule, a person) is turned off again.
    """

    def __init__(self, house: House) -> None:
        self.house = house
        self.mode: Mode | None = None  # mode the thermostats were last switched for
        self.switching: Mode | None = None  # new mode waiting for its thermostats
        self.plan: ZonePlan | None = None
        self._sent: dict[str, tuple[str, float, int]] = {}  # zone: (hvac mode, time, attempts)
        self._failed: set[str] = set()
        self._stray: set[str] = set()
        self._unavailable: tuple[str, ...] = ()

    def _name(self, entity_id: str) -> str:
        return name_of(self.house.hass, entity_id) or entity_id

    def _names(self, zones: Any) -> list[str]:
        return [self._name(z) for z in zones]

    def _log(self, key: str, mode: Mode, **values: Any) -> None:
        house = self.house
        message = zones_message(
            key, mode, house.hass.config.language, not house.control_equipment, **values
        )
        house.activity("Climate Circuits", message, f"{house.entry.entry_id}_mode")

    @callback
    def evaluate(self, decision: ModeDecision) -> None:
        house = self.house
        if not house.settings.switch_zones:
            self.plan = None
            return
        # Before async_start nothing is logged yet; without a source the mode is a guess.
        if not house.logging or decision.source is ModeSource.DEFAULT:
            return
        mode = decision.mode
        heating = [z for c in house.circuits.values() for z in c.settings.heating_zones]
        cooling = [z for c in house.circuits.values() for z in c.settings.cooling_zones]
        hvac_modes = {
            z: state.state if (state := state_of(house.hass, z)) else None
            for z in {*heating, *cooling}
        }
        changed = self.mode is not None and mode is not self.mode
        if changed:
            self.switching = mode if mode is not Mode.OFF else None
            self._sent.clear()
            self._failed.clear()
        self.mode = mode
        plan = self.plan = plan_zones(mode, heating, cooling, hvac_modes, self.switching is mode)
        off, on = self._names(plan.turn_off), self._names(plan.turn_on)

        if changed:
            if off and on:
                self._log("switch", mode, off=off, on=on)
            elif off or on:
                self._log("switch_off" if off else "turn_on", mode, off=off, on=on)
            else:
                self._log("nothing", mode)
        elif stray := [z for z in plan.turn_off if z not in self._stray]:
            self._log("stray", mode, names=", ".join(self._names(stray)))
        self._stray = set(plan.turn_off)
        if plan.unavailable and plan.unavailable != self._unavailable:
            self._log("unavailable", mode, names=", ".join(self._names(plan.unavailable)))
        self._unavailable = plan.unavailable

        if not house.control_equipment:
            self.switching = None  # dry run: nothing waits for thermostats
            return
        for zone in plan.turn_off:
            self._command(zone, OFF, mode)
        if self.switching is mode and not plan.blocked:
            if on and not changed:
                self._log("turn_on", mode, on=on)
            for zone in plan.turn_on:
                self._command(zone, plan.hvac_mode or OFF, mode)
            self.switching = None
        for zone in [z for z, (m, _, _) in self._sent.items() if hvac_modes.get(z) == m]:
            del self._sent[zone]

    @callback
    def _command(self, zone: str, hvac_mode: str, mode: Mode) -> None:
        """Repeated at most every ZONE_COMMAND_RETRY s, reported after the last attempt."""
        hass = self.house.hass
        now = hass.loop.time()
        sent = self._sent.get(zone)
        attempts = sent[2] if sent and sent[0] == hvac_mode else 0
        if sent and attempts and now - sent[1] < ZONE_COMMAND_RETRY:
            return
        if attempts >= ZONE_COMMAND_ATTEMPTS:
            if zone not in self._failed:
                self._failed.add(zone)
                self._log("failed", mode, names=self._name(zone), n=attempts)
            return
        self._sent[zone] = (hvac_mode, now, attempts + 1)
        call_service(hass, "climate", "set_hvac_mode", entity_id=zone, hvac_mode=hvac_mode)

    def details(self) -> dict[str, Any]:
        if (plan := self.plan) is None:
            return {}
        return {
            "zones_must_be_off": other_zones_kind(
                self.mode or Mode.OFF, self.house.hass.config.language
            ),
            "zones_still_on": self._names(plan.turn_off),
            "zones_waiting_to_turn_on": self._names(plan.turn_on) if self.switching else [],
            "zones_failed": self._names(sorted(self._failed)),
        }


class House(Listeners):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__()
        self.hass = hass
        self.entry = entry
        self.settings = HouseSettings.from_options(entry.options)
        self.circuits: dict[str, Circuit] = {}
        self.zones = ZoneSwitcher(self)
        self.hot_water = (
            HotWater(self, self.settings.hot_water) if self.settings.hot_water else None
        )
        self.device_id: str | None = None
        self.override = Override.AUTO
        self.control_equipment = False
        self.last_mode: Mode | None = None
        self.decision = ModeDecision(Mode.OFF, ModeSource.DEFAULT, "not evaluated")
        self.outdoor: float | None = None
        self.logging = False  # Activity starts once entities exist, so entries link to them
        self.started = hass.loop.time()
        self.booting = not hass.is_running  # set up while Home Assistant starts, not a reload
        self.pause = ModePause(self.settings.mode_pause)
        self.pause_remaining = 0.0
        self.persisted: dict[str, Any] = {"pumps": {}, "mixers": {}, "circuits": {}}
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        self._unsubs: list[Callable[[], None]] = []
        self._snapshot = self._config_snapshot()
        self._logged_mode: tuple[Mode, ModeSource] | None = None

    def _config_snapshot(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        entry = self.entry
        return dict(entry.options), {sid: dict(sub.data) for sid, sub in entry.subentries.items()}

    @callback
    def apply_tuning_changes(self) -> bool:
        """Apply curve or circulation tuning in place; False means reload."""
        options, circuits = self._config_snapshot()
        old_options, old_circuits = self._snapshot

        def untuned(data: dict[str, Any]) -> dict[str, Any]:
            hot_water = data.get("hot_water", {})
            return data | {
                "hot_water": {k: v for k, v in hot_water.items() if k not in HOT_WATER_TUNING}
            }

        def no_curves(data: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in data.items() if k not in CURVE_SECTIONS}

        if (
            circuits.keys() != old_circuits.keys()
            or untuned(options) != untuned(old_options)
            or any(no_curves(circuits[s]) != no_curves(old_circuits[s]) for s in circuits)
        ):
            return False
        for subentry_id, data in circuits.items():
            if subentry_id in self.circuits:
                self.circuits[subentry_id].settings = CircuitSettings.from_data(data)
        self.settings = HouseSettings.from_options(options)
        if self.hot_water and self.settings.hot_water:
            self.hot_water.settings = self.settings.hot_water
        self._snapshot = (options, circuits)
        self.evaluate()
        return True

    @property
    def mode(self) -> Mode:
        return self.decision.mode

    @property
    def status(self) -> str:
        return "ok" if self.control_equipment else "dry_run"

    def now(self) -> float:
        """Monotonic seconds; tests replace it."""
        return self.hass.loop.time()

    def wall(self) -> float:
        """Epoch seconds, for what must survive a restart."""
        return time.time()

    def activity(self, name: str, message: str, unique_id: str, platform: str = "sensor") -> None:
        log_activity(self.hass, name, message, entity_id_for(self.hass, platform, unique_id))

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.override = Override(data.get("override", Override.AUTO))
        self.control_equipment = bool(data.get("control_equipment", False))
        if (last := data.get("last_mode")) is not None:
            self.last_mode = Mode(last)
        self.zones.mode = self.last_mode  # a change while HA was down still switches zones
        for key in self.persisted:
            self.persisted[key] = data.get(key, {})
        if pause := data.get("pause"):
            self.pause = ModePause(
                self.settings.mode_pause,
                Mode(pause["active"]) if pause.get("active") else None,
                pause.get("stopped_at"),
            )
        if self.hot_water:
            self.hot_water.enabled = bool(data.get("circulation_enabled", True))

    def _data(self) -> dict[str, Any]:
        return {
            "override": self.override.value,
            "control_equipment": self.control_equipment,
            "last_mode": self.last_mode.value if self.last_mode else None,
            "circulation_enabled": self.hot_water.enabled if self.hot_water else True,
            "pause": {
                "active": self.pause.active.value if self.pause.active else None,
                "stopped_at": self.pause.stopped_at,
            },
            **self.persisted,
        }

    def save(self) -> None:
        self._store.async_delay_save(self._data, 1)

    def inputs(self) -> set[str]:
        s = self.settings
        entities = {*filter(None, [s.mode_entity, s.fallback_sensor, s.outdoor_sensor])}
        entities |= set(s.info_sensors)
        for item in [*self.circuits.values(), *filter(None, [self.hot_water])]:
            entities |= item.inputs()
        return entities

    @callback
    def async_start(self) -> None:
        self.logging = True
        self.started = self.now()
        self._unsubs = [
            async_track_state_change_event(self.hass, list(self.inputs()), self._on_event),
            async_track_time_interval(
                self.hass, self._on_event, timedelta(seconds=EVALUATE_INTERVAL)
            ),
        ]
        for circuit in self.circuits.values():
            circuit.async_start()
        self.evaluate()

    async def async_unload(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()
        for circuit in self.circuits.values():
            circuit.async_stop()
        await self._store.async_save(self._data())

    @callback
    def _on_event(self, _event: Any) -> None:
        self.evaluate()

    @callback
    def evaluate(self) -> None:
        s = self.settings
        entity_mode = None
        if s.mode_entity and (state := self.hass.states.get(s.mode_entity)) is not None:
            entity_mode = mode_from_entity(s.mode_entity.split(".")[0], state.state, s.mapping)
        fallback = float_of(self.hass, s.fallback_sensor)
        self.decision = decision = resolve_mode(
            s.mode, self.override, entity_mode, fallback, self.last_mode
        )
        self._log_mode()
        self.zones.evaluate(decision)
        reliable = decision.source not in (ModeSource.LAST, ModeSource.DEFAULT)
        if reliable and decision.mode is not self.last_mode:
            self.last_mode = decision.mode
            self.save()
        self.outdoor = float_of(self.hass, s.outdoor_sensor)
        before = (self.pause.active, self.pause.stopped_at)
        self.pause_remaining = self.pause.check(self.mode, self.wall()) if reliable else 0.0
        if (self.pause.active, self.pause.stopped_at) != before:
            self.save()
        for circuit in self.circuits.values():
            circuit.evaluate(self.mode, self.outdoor)
        if self.hot_water:
            self.hot_water.evaluate()
        self._notify()

    def _decided_by(self) -> str | None:
        s = self.settings
        return {ModeSource.ENTITY: s.mode_entity, ModeSource.FALLBACK: s.fallback_sensor}.get(
            self.decision.source
        )

    @callback
    def _log_mode(self) -> None:
        """Activity entry when the mode or what decided it changes."""
        d = self.decision
        if not self.logging or (d.mode, d.source) == self._logged_mode:
            return
        self._logged_mode = (d.mode, d.source)
        by = name_of(self.hass, self._decided_by())
        message = mode_message(d.mode, d.source, by, d.reason, self.hass.config.language)
        self.activity("Climate Circuits", message, f"{self.entry.entry_id}_mode")

    def mode_details(self) -> dict[str, Any]:
        """Everything the mode decision looked at."""
        s, d, hass = self.settings, self.decision, self.hass
        details: dict[str, Any] = {
            "source": d.source.value,
            "decided_by": "override"
            if d.source is ModeSource.OVERRIDE
            else name_of(hass, self._decided_by()),
            "reason": d.reason,
            "override": self.override.value,
            "last_mode": self.last_mode.value if self.last_mode else None,
        }
        if s.mode_entity:
            state = hass.states.get(s.mode_entity)
            details["source_entity"] = s.mode_entity
            details["source_state"] = state.state if state else None
            if state is not None and "hvac_action" in state.attributes:
                details["source_action"] = state.attributes["hvac_action"]
        if s.fallback_sensor:
            fallback = float_of(hass, s.fallback_sensor)
            details |= {
                "fallback_sensor": s.fallback_sensor,
                "fallback_temperature": round(fallback, 1) if fallback is not None else None,
                "heat_threshold": s.mode.heat_threshold,
                "cool_threshold": s.mode.cool_threshold,
            }
        details["outdoor_temperature"] = self.outdoor
        details |= self.zones.details()
        for entity_id in s.info_sensors:
            details[name_of(hass, entity_id)] = _describe(hass, entity_id)
        return details

    @callback
    def set_override(self, override: Override) -> None:
        self.override = override
        self.save()
        self.evaluate()

    @callback
    def set_control_equipment(self, on: bool) -> None:
        self.control_equipment = on
        self.save()
        self.evaluate()
