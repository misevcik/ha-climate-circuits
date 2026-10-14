"""A switch the integration commands, with confirmation and repeat."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import callback

from .const import RELAY_ATTEMPTS, RELAY_GRACE, RELAY_RETRY, RELAY_RETRY_RESET
from .core.texts import out_message
from .states import call_service, state_of

if TYPE_CHECKING:
    from .house import House


class Relay:
    """A switch we command; a command counts once the state confirms it, else it is repeated."""

    def __init__(
        self,
        house: House,
        entity_id: str,
        label: str,
        log_to: tuple[str, str] | None = None,  # unique id, platform of the Activity entity
    ) -> None:
        self.house, self.entity_id, self.label = house, entity_id, label
        self._log_to = log_to or (f"{house.entry.entry_id}_mode", "sensor")
        self._sent: tuple[bool, float, int] | None = None  # wanted, time, attempts
        self._reported = False
        self._known: bool | None = None
        self._lost_at: float | None = None
        self._available = True  # as last said in Activity

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

    def available(self) -> bool:
        """False once the relay is unavailable longer than a board blip; Activity on a change.

        While Home Assistant starts the boards may still be connecting: nothing is said then.
        """
        ok = self.shown() is not None
        if ok is not self._available and self.house.logging:
            self._available = ok
            self._log("relay_back" if ok else "relay_unavailable", label=self.label)
        return ok

    @callback
    def command(self, on: bool) -> None:
        """Send the command even when the state already says so: it may be stale (a board blip)."""
        self._sent = (on, self.house.now(), 1)
        call_service(
            self.house.hass,
            self.entity_id.split(".")[0],
            "turn_on" if on else "turn_off",
            entity_id=self.entity_id,
        )

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
            *self._log_to,
        )
