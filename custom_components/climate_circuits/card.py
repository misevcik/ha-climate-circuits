"""Serve the cards (curve, schema) and register them as Lovelace resources.

Not add_extra_js_url: an extra module runs before HA swaps in the scoped custom element
registry and the card gets lost. It stays as the fallback for YAML dashboards.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import CARD_FILES, FRONTEND_URL

_LOGGER = logging.getLogger(__name__)


async def async_register_card(hass: HomeAssistant) -> None:
    if hass.http is None:
        return
    frontend = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(frontend), cache_headers=False)]
    )
    for card in CARD_FILES:
        base = f"{FRONTEND_URL}/{card}"
        url = f"{base}?v={int((frontend / card).stat().st_mtime)}"  # busts the cache
        await _register(hass, base, url)


async def _register(hass: HomeAssistant, base: str, url: str) -> None:
    resources = getattr(hass.data.get("lovelace"), "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        add_extra_js_url(hass, url)
        return
    try:
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
        for item in resources.async_items():
            if item.get("url", "").startswith(base):
                if item["url"] != url:
                    await resources.async_update_item(item["id"], {"url": url})
                return
        await resources.async_create_item({"res_type": "module", "url": url})
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Card resource registration failed, using extra module", exc_info=True)
        add_extra_js_url(hass, url)
