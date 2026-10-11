"""Small readers of Home Assistant state, shared by the runtime and the outputs."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, State

from .const import UNKNOWN_STATES


def state_of(hass: HomeAssistant, entity_id: str | None) -> State | None:
    """State, None when missing or unavailable."""
    state = hass.states.get(entity_id) if entity_id else None
    return None if state is None or state.state in UNKNOWN_STATES else state


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def float_of(hass: HomeAssistant, entity_id: str | None) -> float | None:
    return number(state.state) if (state := state_of(hass, entity_id)) else None


def name_of(hass: HomeAssistant, entity_id: str | None) -> str | None:
    if not entity_id:
        return None
    return state.name if (state := hass.states.get(entity_id)) else entity_id


def call_service(hass: HomeAssistant, domain: str, service: str, **data: Any) -> None:
    hass.async_create_task(hass.services.async_call(domain, service, data))
