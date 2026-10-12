"""The pump and the mixing valve of a circuit.

They switch only while Control equipment and the circuit's own switch are on.

Safety rules for the valve motor: the two relays are never on together, a relay never runs
longer than a full travel plus margin, a move that may be cut short (reload, stop) turns the
relay off, and an unknown position is homed against the end stop before regulating.
"""

from __future__ import annotations

from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    EVALUATE_INTERVAL,
    EXERCISE_PUMP_SECONDS,
    MIXER_HOMING_DELAY,
    MIXER_RUN_MARGIN,
    RELAY_ATTEMPTS,
    RELAY_GRACE,
    RELAY_RETRY,
    RELAY_RETRY_RESET,
    START_GRACE,
)
from .core.mixer import (
    Direction,
    MixerAction,
    MixerSettings,
    hold_reason,
    regulate,
    supply_trend,
)
from .core.mode import Mode
from .core.protect import exercise_due
from .core.pump import PumpDecision, PumpTimer
from .core.texts import mixer_hold_text, mixer_text, out_message, pump_text
from .core.travel import TravelTracker
from .states import call_service, number, state_of

if TYPE_CHECKING:
    from .house import Circuit, House


STOP_CHECK_INTERVAL = 3  # s between looks whether a stopped relay really is off
STOP_CHECKS = 12


class Relay:
    """A switch we command; a command counts once the state confirms it, else it is repeated."""

    def __init__(self, house: House, entity_id: str, label: str) -> None:
        self.house, self.entity_id, self.label = house, entity_id, label
        self._sent: tuple[bool, float, int] | None = None  # wanted, time, attempts
        self._reported = False
        self._known: bool | None = None
        self._lost_at: float | None = None

    def is_on(self) -> bool | None:
        return state.state == "on" if (state := state_of(self.house.hass, self.entity_id)) else None

    def shown(self) -> bool | None:
        """For display: the last known state through a short blip of the relay board."""
        if (current := self.is_on()) is not None:
            self._known, self._lost_at = current, None
            return current
        now = self.house.now()
        if self._lost_at is None:
            self._lost_at = now
        return self._known if now - self._lost_at < RELAY_GRACE else None

    @callback
    def ensure(self, on: bool) -> bool:
        """Command the relay to on or off; True once its state says so."""
        current = self.is_on()
        if current is None:
            return False
        if current is on:
            self._sent, self._reported = None, False
            return True
        now = self.house.now()
        sent = self._sent if self._sent and self._sent[0] is on else (on, -RELAY_RETRY_RESET, 0)
        if now - sent[1] < RELAY_RETRY:
            return False
        if sent[2] >= RELAY_ATTEMPTS:
            if not self._reported:
                self._reported = True
                self._log("relay_failed", label=self.label, n=sent[2])
            if now - sent[1] < RELAY_RETRY_RESET:
                return False
            sent = (on, sent[1], 0)  # not confirmed for a long time: try again
        self._sent = (on, now, sent[2] + 1)
        call_service(
            self.house.hass,
            self.entity_id.split(".")[0],
            "turn_on" if on else "turn_off",
            entity_id=self.entity_id,
        )
        return False

    def _log(self, key: str, **values: Any) -> None:
        house = self.house
        house.activity(
            "Climate Circuits",
            out_message(key, house.hass.config.language, **values),
            f"{house.entry.entry_id}_mode",
        )


class PumpController:
    """Starts when demand lasted long enough for the valves to open; runs on after heating."""

    def __init__(self, circuit: Circuit) -> None:
        s, house = circuit.settings, circuit.house
        self.circuit = circuit
        self.relay = Relay(house, s.pump, f"{circuit.name} pump")
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


class MixerController:
    """Regulates the supply temperature with a three-point valve and tracks its position.

    The position comes from the relay run times (seen on the relays, whoever switched them),
    so in dry run it follows the old automations and shows what this regulation would do.
    """

    def __init__(self, circuit: Circuit) -> None:
        s, house = circuit.settings, circuit.house
        self.circuit = circuit
        self.open = Relay(house, s.mixer_open, f"{circuit.name} mixer open")
        self.close = Relay(house, s.mixer_close, f"{circuit.name} mixer close")
        self.tracker = TravelTracker(s.travel, s.travel)
        self.params = MixerSettings(travel=s.travel, hysteresis=s.hysteresis, settle=s.settle)
        self.state = "idle"  # idle, opening, closing, homing
        self.proposal: MixerAction | None = None
        self._finish: CALLBACK_TYPE | None = None
        self._watchdog: CALLBACK_TYPE | None = None
        self._lost: CALLBACK_TYPE | None = None  # the moving relay is unavailable
        self._last_end_pulse: float | None = None
        self._move_ended: float | None = None  # the regulation waits for it to show
        self._supply: list[tuple[float, float]] = []  # (time, supply) for the trend
        self._source_ref: float | None = None  # source temperature at the last move
        self._proposal_logged: tuple[Any, ...] | None = None
        self._hold_logged: str | None = None  # why it last stayed, not repeated in Activity
        self._unsubs: list[CALLBACK_TYPE] = []
        self._seed()

    @property
    def _max_run(self) -> float:
        return self.params.travel + self.params.end_pulse + MIXER_RUN_MARGIN

    def _seed(self) -> None:
        """Last known position; otherwise the one of the old cover, until the valve is homed."""
        house, s = self.circuit.house, self.circuit.settings
        stored = house.persisted["mixers"].get(self.circuit.id, {})
        if stored.get("position") is not None and not stored.get("moving"):
            self.tracker.set(stored["position"])
        elif cover := state_of(house.hass, s.mixer_position):
            if (position := number(cover.attributes.get("current_position"))) is not None:
                self.tracker.set(position)

    def inputs(self) -> set[str]:
        return {self.open.entity_id, self.close.entity_id}

    def position(self) -> float | None:
        return self.tracker.current(self.circuit.house.now())

    @callback
    def async_start(self) -> None:
        hass = self.circuit.house.hass
        self._unsubs = [
            async_track_state_change_event(
                hass, [self.open.entity_id, self.close.entity_id], self._on_relay
            ),
            async_track_time_interval(hass, self._tick, timedelta(seconds=EVALUATE_INTERVAL)),
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._on_ha_stop),
        ]
        for direction, relay in self._relays():
            if relay.is_on():  # running at the start: how far is unknown
                self.tracker.start(direction, self.circuit.house.now())
                self.tracker.clear()
        house = self.circuit.house
        if house.booting and house.settings.home_mixers_on_start and self.circuit.controlling:
            self.tracker.clear()  # the valve may have been moved while Home Assistant was down

    @callback
    def async_stop(self) -> None:
        """Never leave a relay on because a timer was cancelled."""
        self._persist()
        for cancel in (*self._unsubs, self._finish, self._watchdog, self._lost):
            if cancel:
                cancel()
        self._unsubs, self._finish, self._watchdog, self._lost = [], None, None, None
        if self.circuit.controlling:
            self._all_off()

    def _relays(self) -> tuple[tuple[Direction, Relay], tuple[Direction, Relay]]:
        return (Direction.OPEN, self.open), (Direction.CLOSE, self.close)

    @callback
    def _on_ha_stop(self, _event: Event) -> None:
        self._persist()
        if self.circuit.controlling:
            self._all_off()

    @callback
    def _all_off(self) -> None:
        for _, relay in self._relays():
            if relay.is_on() is not False:
                call_service(
                    self.circuit.house.hass,
                    relay.entity_id.split(".")[0],
                    "turn_off",
                    entity_id=relay.entity_id,
                )

    def _persist(self) -> None:
        house = self.circuit.house
        pos = self.position()
        stored = house.persisted["mixers"].setdefault(self.circuit.id, {})
        stored["position"], stored["moving"] = pos, self.tracker.moving
        house.save()

    @property
    def _language(self) -> str:
        return self.circuit.house.hass.config.language

    def _log_text(self, message: str) -> None:
        circuit = self.circuit
        circuit.house.activity(circuit.name, message, f"{circuit.id}_mixer_position")

    def _log(self, key: str, *, proposal: bool = False, **values: Any) -> None:
        circuit, house = self.circuit, self.circuit.house
        message = out_message(
            key, house.hass.config.language, dry_run=proposal, name=circuit.name, **values
        )
        house.activity(circuit.name, message, f"{circuit.id}_mixer_position")

    @callback
    def _on_relay(self, event: Event[EventStateChangedData]) -> None:
        house = self.circuit.house
        direction = (
            Direction.OPEN if event.data["entity_id"] == self.open.entity_id else Direction.CLOSE
        )
        new, now = event.data["new_state"], house.now()
        old = event.data["old_state"]
        if new is None or new.state not in ("on", "off"):
            if self.tracker.direction is direction and self._lost is None:
                # Boards drop off the network for a moment: lose the move only if it lasts.
                self._lost = async_call_later(house.hass, RELAY_GRACE, self._relay_lost)
            return
        if old is not None and old.state not in ("on", "off"):
            if self.tracker.direction is direction and self._lost is not None:
                self._lost()
                self._lost = None
                if new.state == "on":
                    return  # the relay kept running through the blip
            elif new.state == "off":
                return  # back after a blip while it stood: nothing moved
        if new.state == "on":
            self.tracker.start(direction, now)
            self._arm_watchdog()
            if self.open.is_on() and self.close.is_on() and self.circuit.controlling:
                self._log("mixer_both")
                self._all_off()
        else:
            cut_short = (
                self.state == "homing"
                and self.tracker.moving
                and now - self.tracker.started < self.params.travel * 0.95
            )
            if self.tracker.moving:
                self._move_ended = now
            self.tracker.stop(now)
            if cut_short:  # somebody else switched the relay off: the end stop is not reached
                self.tracker.clear()
                if self._finish:
                    self._finish()
                    self._finish = None
                self.state = "idle"
                self._log("mixer_homing_cut")
            if not (self.open.is_on() or self.close.is_on()):
                self._disarm_watchdog()
            house.persisted["mixers"].setdefault(self.circuit.id, {})["last_move"] = house.wall()
            self._persist()
        self.circuit.refresh()

    @callback
    def _relay_lost(self, _now: Any) -> None:
        self._lost = None
        if self.tracker.moving:
            self.tracker.clear()
            self.circuit.refresh()

    def _arm_watchdog(self) -> None:
        self._disarm_watchdog()
        self._watchdog = async_call_later(self.circuit.house.hass, self._max_run, self._runaway)

    def _disarm_watchdog(self) -> None:
        if self._watchdog:
            self._watchdog()
            self._watchdog = None

    @callback
    def _runaway(self, _now: Any) -> None:
        self._watchdog = None
        if self.circuit.controlling and (self.open.is_on() or self.close.is_on()):
            self._log("mixer_stopped")
            self._all_off()

    @callback
    def _tick(self, _now: Any) -> None:
        circuit, house = self.circuit, self.circuit.house
        now = house.now()
        controlling = circuit.controlling
        if not controlling and self.tracker.position is None and not self.tracker.moving:
            self._seed()  # the old cover may not have existed yet when the integration started
        position = self.tracker.current(now)
        if controlling and self._busy:
            return
        if controlling:
            if self.open.is_on() is None or self.close.is_on() is None:
                return
            if (self.open.is_on() or self.close.is_on()) and not self.tracker.moving:
                self._log("mixer_stray")
                self._all_off()
                return
            last_move = house.persisted["mixers"].get(circuit.id, {}).get("last_move")
            if not circuit.output_demand and exercise_due(
                last_move, house.wall(), house.settings.exercise_days
            ):
                self.tracker.clear()  # idle for days: find the end stop again
                position = None
        if position is None:  # nothing to regulate until the end stop is found
            if controlling and now - house.started >= MIXER_HOMING_DELAY:
                self._home()
            return
        if not circuit.output_demand and now - house.started < START_GRACE:
            return  # the zones may not be loaded yet: no closing for lack of demand
        target = circuit.target.value if circuit.target else None
        supply = circuit.supply_temperature()
        if supply is not None:
            self._supply = [(t, v) for t, v in self._supply if now - t <= 600] + [(now, supply)]
        source = circuit.source_temperature()
        if source is None or self._source_ref is None:
            self._source_ref = source  # (re)start from here: no jump when the sensor returns
        since_move = None if self._move_ended is None else now - self._move_ended
        trend = supply_trend(self._supply, now, self.params.trend_window)
        action = regulate(
            heating=house.mode is Mode.HEAT,
            demand=circuit.output_demand,
            target=target,
            supply=supply,
            position=position,
            since_end_pulse=None if self._last_end_pulse is None else now - self._last_end_pulse,
            settings=self.params,
            since_move=since_move,
            trend=trend,
            source=source,
            source_ref=self._source_ref,
        )
        if action is None:
            hold = hold_reason(
                demand=circuit.output_demand,
                target=target,
                supply=supply,
                position=position,
                settings=self.params,
                since_move=since_move,
                trend=trend,
            )
            if hold and hold[0] != self._hold_logged and house.logging:
                house.activity(
                    circuit.name,
                    mixer_hold_text(hold[0], hold[1], circuit.name, house.hass.config.language),
                    f"{circuit.id}_mixer_position",
                )
            if hold:
                self._hold_logged = hold[0]
        else:
            self._hold_logged = None
        self.proposal = action
        if controlling and action:
            if self._execute(action, now):
                self._source_ref = source
        elif not controlling:
            self._log_proposal(action)
            if action:
                self._source_ref = source
        circuit.refresh()

    @property
    def _busy(self) -> bool:
        return self._finish is not None

    def _log_proposal(self, action: MixerAction | None) -> None:
        """Dry run: say what the regulation would do, once per kind of move."""
        key = None if action is None else (action.direction, action.end_pulse, action.homing)
        if key != self._proposal_logged:
            self._proposal_logged = key
            if action is not None and self.circuit.house.logging:
                self._log_text(mixer_text(action, self.circuit.name, self._language, dry_run=True))

    def _execute(self, action: MixerAction, now: float) -> bool:
        """True when the move started."""
        if action.homing:
            self._home()
            return False
        if not self._run(action.direction, action.seconds, homing=False):
            return False
        if action.end_pulse:
            self._last_end_pulse = now
        self._log_text(mixer_text(action, self.circuit.name, self._language))
        return True

    def _run(self, direction: Direction, seconds: float, *, homing: bool) -> bool:
        """Start a move; the other relay must be off first."""
        relay = self.open if direction is Direction.OPEN else self.close
        other = self.close if direction is Direction.OPEN else self.open
        if other.is_on() is not False:
            other.ensure(False)
            return False  # try again at the next tick
        self.state = (
            "homing" if homing else ("opening" if direction is Direction.OPEN else "closing")
        )
        relay.ensure(True)
        self.circuit.refresh()
        self._finish = async_call_later(
            self.circuit.house.hass,
            min(seconds, self._max_run),
            partial(self._stop_run, relay, homing, 0),
        )
        return True

    @callback
    def _stop_run(self, relay: Relay, homing: bool, tries: int, _now: Any = None) -> None:
        relay.ensure(False)
        if relay.is_on() is not False and tries < STOP_CHECKS:
            self._finish = async_call_later(
                self.circuit.house.hass,
                STOP_CHECK_INTERVAL,
                partial(self._stop_run, relay, homing, tries + 1),
            )
            return
        self._finish = None
        self.state = "idle"
        if homing:
            self.tracker.set(0.0)
            self._last_end_pulse = self.circuit.house.now()  # homing ended with one
            self.circuit.house.persisted["mixers"].setdefault(self.circuit.id, {})["last_move"] = (
                self.circuit.house.wall()
            )
            self._log("mixer_homed")
        self._persist()
        self.circuit.refresh()

    def _home(self) -> None:
        """Close against the end stop; the full travel plus the end pulse from any position."""
        if self._run(Direction.CLOSE, self.params.travel + self.params.end_pulse, homing=True):
            self._log("mixer_homing")

    def status(self) -> str:
        """idle, opening, closing, homing, or unknown while the position is not known."""
        if self.state == "homing":
            return "homing"
        if self.tracker.moving:
            return "opening" if self.tracker.direction is Direction.OPEN else "closing"
        return "idle" if self.position() is not None else "unknown"

    def details(self) -> dict[str, Any]:
        return {
            "movement": self.status(),
            "position_known": self.position() is not None,
            "proposed": (
                mixer_text(self.proposal, self.circuit.name, self._language)
                if self.proposal
                else None
            ),
        }
