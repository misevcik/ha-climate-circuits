"""The circulation pump of a circuit: starts when demand lasted long enough, runs on after.

It switches only while Control equipment and the circuit's own switch are on."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import callback

from .const import EXERCISE_PUMP_SECONDS, START_GRACE
from .core.mode import Mode
from .core.protect import exercise_due
from .core.pump import PumpDecision, PumpTimer
from .core.texts import pump_text
from .relay import Relay

if TYPE_CHECKING:
    from .circuit import Circuit


class PumpController:
    """Starts when demand lasted long enough for the valves to open; runs on after heating."""

    def __init__(self, circuit: Circuit) -> None:
        s, house = circuit.settings, circuit.house
        self.circuit = circuit
        log_to = (f"{circuit.id}_pump", "binary_sensor")
        self.relay = Relay(house, s.pump, f"{circuit.name} pump", log_to)
        self.timer = PumpTimer(s.pump_delay, s.pump_run_on)
        self.decision: PumpDecision | None = None
        self._exercise_until = 0.0
        self._was_running = False
        self._logged: tuple[Any, ...] | None = None

    def inputs(self) -> set[str]:
        return {self.relay.entity_id}

    @callback
    def evaluate(self) -> None:
        circuit, house = self.circuit, self.circuit.house
        now, wall = house.now(), house.wall()
        self.relay.available()  # Activity when the relay drops out and when it is back
        running = self.relay.is_on()
        stored = house.persisted["pumps"].setdefault(circuit.id, {})
        if running or "last_on" not in stored:
            stored["last_on"] = wall
        if self._was_running and not running:
            house.save()
        self._was_running = bool(running)
        demand = circuit.output_demand
        if not demand and running and now - house.started < START_GRACE:
            return  # the zones may not be loaded yet: keep a running pump as it is
        if (
            circuit.controlling
            and not demand
            and not running
            and self._exercise_until <= now
            and exercise_due(stored["last_on"], wall, house.settings.exercise_days)
        ):
            self._exercise_until = now + EXERCISE_PUMP_SECONDS
        self.decision = self.timer.update(
            now,
            demand,
            house.mode is Mode.HEAT,
            bool(running),
            max(self._exercise_until - now, 0.0),
        )
        self._log_change()
        if circuit.controlling:
            self.relay.ensure(self.decision.on)

    def text(self) -> str | None:
        if self.decision is None:
            return None
        house = self.circuit.house
        return pump_text(
            self.decision,
            self.circuit.blocked,
            house.hass.config.language,
            dry_run=not self.circuit.controlling,
        )

    @callback
    def _log_change(self) -> None:
        """Activity entry when the pump starts, stops or waits for another reason."""
        decision, house = self.decision, self.circuit.house
        if not house.logging or decision is None:
            return
        key = (decision.on, decision.reason, self.circuit.blocked and self.circuit.blocked.block)
        if key != self._logged:
            self._logged = key
            house.activity(
                self.circuit.name, self.text() or "", f"{self.circuit.id}_pump", "binary_sensor"
            )
