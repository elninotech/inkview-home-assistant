"""Sidebar panel registration (custom panel, JS from `public/panel/`)."""
from __future__ import annotations

import logging

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from .const import (
    DATA_PANEL_REGISTERED,
    DOMAIN,
    PANEL_ICON,
    PANEL_MODULE_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _registered(hass: HomeAssistant) -> bool:
    return bool(hass.data.get(DOMAIN, {}).get(DATA_PANEL_REGISTERED))


def async_register_panel(hass: HomeAssistant) -> None:
    """Idempotent; called once per enabled config entry."""
    if _registered(hass):
        return
    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            require_admin=False,
            config={
                "_panel_custom": {
                    "name": "inkview-panel",
                    "module_url": f"{PANEL_MODULE_URL}?v={VERSION}",
                    "embed_iframe": False,
                    "trust_external": False,
                }
            },
        )
    except ValueError:
        # Raised when the url_path is already taken; treat as registered.
        _LOGGER.debug("InkView panel was already registered; reusing it")
    hass.data.setdefault(DOMAIN, {})[DATA_PANEL_REGISTERED] = True


def async_unregister_panel(hass: HomeAssistant) -> None:
    if not _registered(hass):
        return
    try:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
    except Exception as e:  # noqa: BLE001
        _LOGGER.debug("InkView panel unregister failed (ignored): %s", e)
    hass.data.setdefault(DOMAIN, {})[DATA_PANEL_REGISTERED] = False
