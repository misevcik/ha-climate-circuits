"""Hot water circulation: the pump keeps the circulation return between two temperatures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import callback

from .const import HOT_WATER_GRACE
from .core.circulation import CirculationDecision, CirculationReason, circulation_decision
from .core.texts import circulation_message
from .listeners import Listeners
from .relay import Relay
from .settings import HotWaterSettings
from .states import float_of, state_of

if TYPE_CHECKING:
    from .house import House


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
