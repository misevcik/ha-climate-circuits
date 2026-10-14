"""Runtime of one house: reads entities, decides, notifies entities, writes Activity.

Outputs act only while control_equipment is on (circuit pumps and mixers also need the
circuit's own switch); otherwise the decision is a dry run shown in Activity.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store

from .activity import entity_id_for, log_activity
from .circuit import Circuit
from .const import CURVE_SECTIONS, EVALUATE_INTERVAL, HOT_WATER_TUNING, STORAGE_KEY, STORAGE_VERSION
from .core.mode import Mode, ModeDecision, ModeSource, Override, mode_from_entity, resolve_mode
from .core.protect import ModePause
from .core.texts import mode_message
from .hot_water import HotWater
from .listeners import Listeners
from .settings import CircuitSettings, HouseSettings
from .source import Source
from .states import float_of, name_of
from .zone_switcher import ZoneSwitcher


class House(Listeners):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__()
        self.hass = hass
        self.entry = entry
        self.settings = HouseSettings.from_options(entry.options)
        self.circuits: dict[str, Circuit] = {}
        self.sources: dict[str, Source] = {}
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
        self.persisted: dict[str, Any] = {"pumps": {}, "mixers": {}, "circuits": {}, "sources": {}}
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
        for item in [
            *self.sources.values(),
            *self.circuits.values(),
            *filter(None, [self.hot_water]),
        ]:
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
        for source in self.sources.values():
            source.refresh()
        for circuit in self.circuits.values():
            circuit.evaluate(self.mode, self.outdoor)
        for source in self.sources.values():
            source.evaluate_setpoint(self.mode)
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
        return details | self.zones.details()

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
