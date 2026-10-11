"""Describe Climate Circuits activity events for the logbook."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_ACTIVITY


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    @callback
    def describe(event: Event) -> dict[str, Any]:
        data = event.data
        entry = {LOGBOOK_ENTRY_NAME: data["name"], LOGBOOK_ENTRY_MESSAGE: data["message"]}
        if entity_id := data.get("entity_id"):
            entry[LOGBOOK_ENTRY_ENTITY_ID] = entity_id
        return entry

    async_describe_event(DOMAIN, EVENT_ACTIVITY, describe)
