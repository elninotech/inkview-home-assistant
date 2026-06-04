"""Redacted diagnostics dump (Settings → Devices → Download diagnostics)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SECRET,
    DATA_COORDINATORS,
    DATA_SESSIONS,
    DOMAIN,
)

REDACT_KEYS = {CONF_SECRET, "secret", "access_token", "Authorization"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {})
    coordinator = data.get(DATA_COORDINATORS, {}).get(entry.entry_id)
    sessions = data.get(DATA_SESSIONS, {})

    session_dumps: list[dict[str, Any]] = []
    for iid, s in sessions.items():
        stats = s.get("stats")
        session_dumps.append(
            {
                "instance_id": iid,
                "allowed_entities_count": len(s.get("allowed_entities") or []),
                "key_version": s.get("key_version", 1),
                "stats": stats.snapshot() if stats is not None else None,
            }
        )

    return {
        "entry": async_redact_data(dict(entry.data), REDACT_KEYS),
        "options": async_redact_data(dict(entry.options), REDACT_KEYS),
        "sessions": session_dumps,
        "coordinator": {
            "has_data": coordinator is not None and coordinator.data is not None,
            "last_update_success": coordinator.last_update_success
            if coordinator is not None
            else None,
        },
    }
