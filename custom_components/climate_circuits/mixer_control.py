"""The mixing valve of a circuit, driven by two relays.

They switch only while Control equipment and the circuit's own switch are on.

Safety rules for the valve motor: the two relays are never on together, a relay never runs
longer than a full travel plus margin, a move that may be cut short (reload, stop) turns the
relay off, and an unknown position is homed against the end stop before regulating."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, NamedTuple

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    EVALUATE_INTERVAL,
    MIXER_HOMING_DELAY,
    MIXER_RUN_MARGIN,
    RELAY_GRACE,
    START_GRACE,
    STARVED_AFTER,
)
from .core.mixer import Direction, MixerAction, hold_reason, regulate, starved, supply_trend
from .core.mode import Mode
from .core.protect import exercise_due
from .core.texts import mixer_hold_text, mixer_text, out_message, starved_text
from .core.travel import TravelTracker
from .relay import Relay
from .states import call_service, number, state_of
from .tuning import tuned

if TYPE_CHECKING:
    from .circuit import Circuit


STOP_CHECK_INTERVAL = 3  # s between looks whether a stopped relay really is off
STOP_CHECKS = 12


class _Inputs(NamedTuple):
    """What one regulation step looks at."""

    target: float | None
    supply: float | None
    source: float | None
    since_move: float | None
    trend: float | None


class MixerController:
    """Regulates the supply temperature with a three-point valve and tracks its position.

    The position comes from the relay run times (seen on the relays, whoever switched them),
    so in dry run it follows the old automations and shows what this regulation would do.
    """

    def __init__(self, circuit: Circuit) -> None:
        s, house = circuit.settings, circuit.house
        self.circuit = circuit
        log_to = (f"{circuit.id}_mixer_position", "sensor")
        self.open = Relay(house, s.mixer_open, f"{circuit.name} mixer open", log_to)
        self.close = Relay(house, s.mixer_close, f"{circuit.name} mixer close", log_to)
        self.tracker = TravelTracker(s.mixer.travel, s.mixer.travel)
        self.retune()
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
        self._starved_since: float | None = None  # fully open and below the target
        self.starved = False  # reported: the heat source is not enough
        self._unsubs: list[CALLBACK_TYPE] = []
        self._seed()

    def retune(self) -> None:
        """The regulation as set on the circuit's device."""
        c = self.circuit
        self.params = replace(
            c.settings.mixer,
            travel=tuned(c, "travel"),
            hysteresis=tuned(c, "hysteresis"),
            settle=tuned(c, "settle"),
            gain=tuned(c, "gain"),
            min_step=int(tuned(c, "min_step")),
            max_step=int(tuned(c, "max_step")),
            trend_window=tuned(c, "trend_window"),
            compensate=bool(tuned(c, "source_compensation")),
            min_source_gap=tuned(c, "min_source_gap"),
        )
        self.tracker.travel_open = self.tracker.travel_close = self.params.travel

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
        if house.booting and tuned(house, "home_mixers_on_start") and self.circuit.controlling:
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
            elif self.circuit.controlling and not self._busy:
                # Not a move of ours: a command that came late through a board blip after the
                # move had ended, or somebody else. Stop it now, not after the full travel.
                self._log("mixer_stray")
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
            if self.circuit.house.logging:
                self._log("mixer_move_lost")
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
        """Every EVALUATE_INTERVAL: guard the relays, find the end stop if needed, regulate."""
        circuit, house = self.circuit, self.circuit.house
        now = house.now()
        if not circuit.controlling and self.tracker.position is None and not self.tracker.moving:
            self._seed()  # the old cover may not have existed yet when the integration started
        relays_available = all([relay.available() for _, relay in self._relays()])
        if circuit.controlling:
            if self._busy:
                return
            if not self._relays_ready(relays_available):
                circuit.refresh()
                return
            self._forget_position_after_idle_days()
        position = self.tracker.current(now)
        if position is None:  # nothing to regulate until the end stop is found
            if circuit.controlling and now - house.started >= MIXER_HOMING_DELAY:
                self._home()
            return
        if not circuit.output_demand and now - house.started < START_GRACE:
            return  # the zones may not be loaded yet: no closing for lack of demand
        inputs = self._read_inputs(now)
        action = regulate(
            heating=house.mode is Mode.HEAT,
            demand=circuit.output_demand,
            target=inputs.target,
            supply=inputs.supply,
            position=position,
            since_end_pulse=None if self._last_end_pulse is None else now - self._last_end_pulse,
            settings=self.params,
            since_move=inputs.since_move,
            trend=inputs.trend,
            source=inputs.source,
            source_ref=self._source_ref,
        )
        self._log_hold(action, position, inputs)
        self._check_starved(now, position, inputs.supply, inputs.target, inputs.source)
        self.proposal = action
        self._act(action, now, inputs.source)
        circuit.refresh()

    def _relays_ready(self, available: bool) -> bool:
        """Both relays known and off; one that runs without a move of ours is stopped."""
        if not available or self.open.is_on() is None or self.close.is_on() is None:
            return False  # nothing can be moved; a lost move is homed once the relays are back
        if (self.open.is_on() or self.close.is_on()) and not self.tracker.moving:
            self._log("mixer_stray")
            self._all_off()
            return False
        return True

    def _forget_position_after_idle_days(self) -> None:
        """A valve that has not moved for days is homed: it finds its end stop again."""
        circuit, house = self.circuit, self.circuit.house
        last_move = house.persisted["mixers"].get(circuit.id, {}).get("last_move")
        if not circuit.output_demand and exercise_due(
            last_move, house.wall(), tuned(house, "exercise_days")
        ):
            self.tracker.clear()

    def _read_inputs(self, now: float) -> _Inputs:
        circuit = self.circuit
        supply = circuit.supply_temperature()
        if supply is not None:
            self._supply = [(t, v) for t, v in self._supply if now - t <= 600] + [(now, supply)]
        source = circuit.source_temperature()
        if source is None or self._source_ref is None:
            self._source_ref = source  # (re)start from here: no jump when the sensor returns
        return _Inputs(
            target=circuit.target.value if circuit.target else None,
            supply=supply,
            source=source,
            since_move=None if self._move_ended is None else now - self._move_ended,
            trend=supply_trend(self._supply, now, self.params.trend_window),
        )

    def _log_hold(self, action: MixerAction | None, position: float, inputs: _Inputs) -> None:
        """Activity: why the valve stays, once per reason."""
        if action is not None:
            self._hold_logged = None
            return
        hold = hold_reason(
            demand=self.circuit.output_demand,
            target=inputs.target,
            supply=inputs.supply,
            position=position,
            settings=self.params,
            since_move=inputs.since_move,
            trend=inputs.trend,
        )
        if hold is None:
            return
        key, values = hold
        if key != self._hold_logged and self.circuit.house.logging:
            self._log_text(mixer_hold_text(key, values, self.circuit.name, self._language))
        self._hold_logged = key

    def _act(self, action: MixerAction | None, now: float, source: float | None) -> None:
        """Move the valve, or in dry run say what would move."""
        if self.circuit.controlling:
            moved = action is not None and self._execute(action, now)
        else:
            self._log_proposal(action)
            moved = action is not None
        if moved:
            self._source_ref = source  # the next compensation counts from here

    def _check_starved(
        self,
        now: float,
        position: float | None,
        supply: float | None,
        target: float | None,
        source: float | None,
    ) -> None:
        """Activity entry when the valve stays fully open below the target, and when it ends."""
        circuit, house = self.circuit, self.circuit.house
        if starved(
            heating=house.mode is Mode.HEAT,
            demand=circuit.output_demand,
            position=position,
            supply=supply,
            target=target,
            settings=self.params,
        ):
            if self._starved_since is None:
                self._starved_since = now
            if self.starved or now - self._starved_since < STARVED_AFTER:
                return
            self.starved = True
            heat_source = circuit.source()
            message = starved_text(
                True,
                circuit.name,
                self._language,
                minutes=(now - self._starved_since) / 60,
                supply=supply,
                target=target,
                source=heat_source.name if heat_source else None,
                temperature=source,
                setpoint=heat_source.setpoint() if heat_source else None,
            )
        else:
            self._starved_since = None
            fed = (
                supply is not None
                and target is not None
                and supply >= target - self.params.hysteresis
            )
            if not self.starved or not (fed or not circuit.output_demand):
                return
            self.starved = False
            message = starved_text(
                False, circuit.name, self._language, supply=supply, target=target
            )
        if house.logging:
            self._log_text(message)

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
        # The move counts as ours before the command: its "on" may come back at once.
        self._finish = async_call_later(
            self.circuit.house.hass,
            min(seconds, self._max_run),
            partial(self._stop_run, relay, homing, 0),
        )
        relay.ensure(True)
        self.circuit.refresh()
        return True

    @callback
    def _stop_run(self, relay: Relay, homing: bool, tries: int, _now: Any = None) -> None:
        if tries == 0:
            relay.command(False)  # also when the state says off: the start may not be reported yet
        else:
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
        """idle, opening, closing, homing, unknown (position) or unavailable (a relay)."""
        if self.open.shown() is None or self.close.shown() is None:
            return "unavailable"
        if self.state == "homing":
            return "homing"
        if self.tracker.moving:
            return "opening" if self.tracker.direction is Direction.OPEN else "closing"
        return "idle" if self.position() is not None else "unknown"

    def details(self) -> dict[str, Any]:
        return {
            "movement": self.status(),
            "position_known": self.position() is not None,
            "source_not_enough": self.starved,
            "proposed": (
                mixer_text(self.proposal, self.circuit.name, self._language)
                if self.proposal
                else None
            ),
        }
