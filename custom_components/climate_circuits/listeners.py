"""Objects the entities listen to: they say when their state changed."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import callback


class Listeners:
    """Entities register a callback; _notify calls them after an evaluation."""

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
