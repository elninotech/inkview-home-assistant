"""WebSocket commands for the sidebar panel. `credentials` returns the shared
secret, so it is admin-only; `energy_summary` is open to all (grant-limited)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import CONF_LINK_EXPIRES_AT, DATA_SESSIONS, DOMAIN, ENERGY_PERIODS
from .energy.summary import async_energy_summary
from .grant import combined_grant

_LOGGER = logging.getLogger(__name__)

WS_TYPE_CREDENTIALS = f"{DOMAIN}/credentials"
WS_TYPE_ENERGY_SUMMARY = f"{DOMAIN}/energy_summary"


@callback
def _credentials_payload(hass: HomeAssistant) -> dict[str, list[dict[str, Any]]]:
    sessions = hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
    out: list[dict[str, Any]] = []
    for instance_id, session in sessions.items():
        entry = hass.config_entries.async_get_entry(session.get("entry_id"))
        secret: bytes = session.get("secret", b"")
        out.append(
            {
                "instance_id": instance_id,
                # Live secret: reflects rotation without a reload.
                "secret": secret.hex(),
                "title": (entry.title if entry else None) or "InkView",
                "entry_id": session.get("entry_id"),
                "link_expires_at": session.get(CONF_LINK_EXPIRES_AT),
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
    connection.send_result(msg["id"], _credentials_payload(hass))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ENERGY_SUMMARY,
        vol.Optional("period", default="today"): vol.In(ENERGY_PERIODS),
    }
)
@websocket_api.async_response
async def websocket_energy_summary(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    sessions = hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
    try:
        result = await async_energy_summary(
            hass, msg["period"], combined_grant(sessions.values())
        )
    except Exception:  # noqa: BLE001 — never leak internals to the browser
        _LOGGER.exception("energy summary failed")
        connection.send_error(
            msg["id"], "energy_unavailable", "Energy data is unavailable"
        )
        return
    connection.send_result(msg["id"], result)


@callback
def async_register_ws(hass: HomeAssistant) -> None:
    """Not idempotent; the caller gates on a hass.data flag."""
    websocket_api.async_register_command(hass, websocket_credentials)
    websocket_api.async_register_command(hass, websocket_energy_summary)
