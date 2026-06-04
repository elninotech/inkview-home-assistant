"""WebSocket commands for the InkView sidebar panel.

Backs the panel's "Connect to InkView" card, which surfaces the instance_id
and shared secret so the user can paste them into the InkView server form
without digging through the config entry.

SECURITY — credential exposure gate
-----------------------------------
`inkview/credentials` returns the HMAC shared secret, which can mint
read-only bearer tokens for every allowed sensor, so it is **admin-gated**
via `@websocket_api.require_admin`. Non-admin users get an `unauthorized`
error and the panel hides its credentials card for them. The rest of the
panel (the total-energy view) stays visible to all authenticated users.
"""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DATA_SESSIONS, DOMAIN

_LOGGER = logging.getLogger(__name__)

WS_TYPE_CREDENTIALS = f"{DOMAIN}/credentials"


@callback
def _credentials_payload(hass: HomeAssistant) -> dict[str, list[dict[str, str]]]:
    sessions = hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
    out: list[dict[str, str]] = []
    for instance_id, session in sessions.items():
        entry = hass.config_entries.async_get_entry(session.get("entry_id"))
        secret: bytes = session.get("secret", b"")
        out.append(
            {
                "instance_id": instance_id,
                # Live secret — reflects rotation without a reload.
                "secret": secret.hex(),
                "title": (entry.title if entry else None) or "InkView",
                "entry_id": session.get("entry_id"),
            }
        )
    return {"sessions": out}


@websocket_api.websocket_command(
    {vol.Required("type"): WS_TYPE_CREDENTIALS}
)
@websocket_api.require_admin
@callback
def websocket_credentials(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return instance_id + shared secret for every configured InkView session."""
    connection.send_result(msg["id"], _credentials_payload(hass))


@callback
def async_register_ws(hass: HomeAssistant) -> None:
    """Register InkView websocket commands. Caller gates on a hass.data flag
    so two config entries don't double-register."""
    websocket_api.async_register_command(hass, websocket_credentials)
