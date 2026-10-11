"""Activity (logbook) entries; logbook.py describes the event."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, EVENT_ACTIVITY


@callback
def entity_id_for(hass: HomeAssistant, platform: str, unique_id: str) -> str | None:
    """Linking the entry to our entity shows it in the device's Activity."""
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


@callback
def log_activity(hass: HomeAssistant, name: str, message: str, entity_id: str | None) -> None:
    hass.bus.async_fire(EVENT_ACTIVITY, {"name": name, "message": message, "entity_id": entity_id})
