"""A circuit: its zones, demand, target water from the weather curve, protections, and its
pump and mixing valve."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant, callback

from .const import DEW_POINT_MARGIN, SOURCE_HEADROOM
from .core.curve import WaterTarget, water_target, worst_dew_point
from .core.demand import Demand, circuit_demand
from .core.explain import CircuitExplanation, ZoneSnapshot, explain_circuit
from .core.mode import Mode
from .core.protect import Block, Blocked, CondensationGuard
from .core.texts import circuit_reason, source_text
from .listeners import Listeners
from .mixer_control import MixerController
from .pump_control import PumpController
from .settings import CircuitSettings
from .states import float_of, name_of, number, state_of

if TYPE_CHECKING:
    from .house import House
    from .source import Source


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
        self._short: bool | None = None  # the source set too low for the target

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
            *filter(None, [s.supply_sensor, s.mixer_position]),
            *(self.pump.inputs() if self.pump else ()),
            *(self.mixer.inputs() if self.mixer else ()),
        }

    def mixer_position(self) -> float | None:
        """Position in %: tracked by the mixer controller, else read from the old cover."""
        if self.mixer:
            return self.mixer.position()
        state = state_of(self.house.hass, self.settings.mixer_position)
        return number(state.attributes.get("current_position")) if state else None

    def linked_entities(self) -> dict[str, Any]:
        """What the circuit reads and switches, by role: shown on its device."""
        s, source = self.settings, self.source()
        return {
            "heating_zones": list(s.heating_zones),
            "cooling_zones": list(s.cooling_zones),
            "humidity_sensors": list(s.humidity_sensors),
            "pump": s.pump,
            "mixer_open": s.mixer_open,
            "mixer_close": s.mixer_close,
            "supply_sensor": s.supply_sensor,
            "mixer_position": s.mixer_position,
            "heat_source": source.name if source else None,
        }

    def retune(self) -> None:
        if self.pump:
            self.pump.retune()
        if self.mixer:
            self.mixer.retune()

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

    def source(self) -> Source | None:
        """The chosen heat source; the only one in the house when none is chosen."""
        sources = self.house.sources
        if self.settings.source:
            return sources.get(self.settings.source)
        return next(iter(sources.values())) if len(sources) == 1 else None

    def source_temperature(self) -> float | None:
        """Water coming to the mixer (buffer tank, heat pump), when known."""
        source = self.source()
        return source.temperature() if source else None

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
        self._check_source_headroom(mode)
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

    def source_headroom(self) -> float | None:
        """K the heat source is set above this circuit's target water, when both are known."""
        source = self.source()
        setpoint = source.setpoint() if source else None
        if setpoint is None or self.target is None:
            return None
        return setpoint - self.target.value

    @callback
    def _check_source_headroom(self, mode: Mode) -> None:
        """Activity entry when the heat source is set too low for the target, and when not."""
        headroom = self.source_headroom()
        if not self.house.logging or mode is not Mode.HEAT or not self.demand.active:
            return
        if headroom is None:
            return
        short = headroom < SOURCE_HEADROOM
        if short == self._short:
            return
        first = self._short is None
        self._short = short
        if first and not short:
            return  # nothing to say while it is enough
        source = self.source()
        house = self.house
        house.activity(
            self.name,
            source_text(
                "short" if short else "enough",
                self.name,
                source.name if source else "",
                source.setpoint() if source else None,
                self.target.value if self.target else None,
                house.hass.config.language,
            ),
            f"{self.id}_target_water_temperature",
        )

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
