"""InkView integration entry point."""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from typing import Any

from homeassistant.components.logbook import async_log_entry
from homeassistant.components.persistent_notification import (
    async_create as async_create_notification,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.service import async_register_admin_service

from .const import (
    CONF_INSTANCE_ID,
    CONF_KEY_VERSION,
    CONF_LINK_EXPIRES_AT,
    CONF_SECRET,
    CONF_SHOW_SIDEBAR_PANEL,
    DATA_COORDINATORS,
    DATA_NONCE_CACHES,
    DATA_PANEL_REGISTERED,
    DATA_SERVICES_REGISTERED,
    DATA_SESSIONS,
    DATA_VIEWS_REGISTERED,
    DATA_WS_REGISTERED,
    DOMAIN,
    LINK_CHECK_INTERVAL_MINUTES,
    SERVICE_EXTEND_LINK,
    SERVICE_REFRESH,
    SERVICE_REVOKE_ALL_TOKENS,
    SERVICE_ROTATE_SECRET,
)
from .auth.stats import SessionStats
from .energy.coordinator import InkViewEnergyCoordinator
from .grant import entry_grant
from .http_views import register_views
from .link import (
    async_clear_link_issues,
    async_update_link_issues,
    entry_link_expiry,
    new_link_expiry,
)
from .panel import async_register_panel, async_unregister_panel
from .ws_api import async_register_ws

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# UI-only integration; satisfies hassfest and rejects YAML under `inkview:`.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _ensure_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    return hass.data.setdefault(
        DOMAIN,
        {
            DATA_SESSIONS: {},
            DATA_NONCE_CACHES: {},
            DATA_COORDINATORS: {},
            DATA_VIEWS_REGISTERED: False,
            DATA_SERVICES_REGISTERED: False,
            DATA_PANEL_REGISTERED: False,
            DATA_WS_REGISTERED: False,
        },
    )


def _panel_enabled(entry: ConfigEntry) -> bool:
    if CONF_SHOW_SIDEBAR_PANEL in entry.options:
        return bool(entry.options[CONF_SHOW_SIDEBAR_PANEL])
    return bool(entry.data.get(CONF_SHOW_SIDEBAR_PANEL, True))


def _panel_wanted(hass: HomeAssistant, exclude_entry_id: str | None = None) -> bool:
    return any(
        _panel_enabled(e) and not e.disabled_by
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != exclude_entry_id
    )


def build_session(entry: ConfigEntry) -> dict[str, Any]:
    """Live session the HTTP views authenticate against."""
    grant = entry_grant(entry)
    return {
        "entry_id": entry.entry_id,
        "secret": bytes.fromhex(entry.data[CONF_SECRET]),
        "all_sensors": grant is None,
        "allowed_entities": grant or [],
        "key_version": int(entry.data.get(CONF_KEY_VERSION, 1)),
        CONF_LINK_EXPIRES_AT: entry_link_expiry(entry),
        "stats": SessionStats(),
    }


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    _ensure_domain_data(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = _ensure_domain_data(hass)

    if not data[DATA_VIEWS_REGISTERED]:
        await register_views(hass)
        data[DATA_VIEWS_REGISTERED] = True

    if not data[DATA_SERVICES_REGISTERED]:
        _register_services(hass)
        data[DATA_SERVICES_REGISTERED] = True

    if not data[DATA_WS_REGISTERED]:
        async_register_ws(hass)
        data[DATA_WS_REGISTERED] = True

    # Backfill a missing expiry before attaching the update listener, so the
    # write doesn't trigger a reload.
    if entry_link_expiry(entry) is None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_LINK_EXPIRES_AT: new_link_expiry()}
        )

    data[DATA_SESSIONS][entry.data[CONF_INSTANCE_ID]] = build_session(entry)

    coordinator = InkViewEnergyCoordinator(hass, entry_grant(entry))
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:  # noqa: BLE001
        _LOGGER.warning(
            "InkView initial energy refresh failed (will retry): %s", e
        )
    data[DATA_COORDINATORS][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if _panel_enabled(entry):
        async_register_panel(hass)

    @callback
    def _check_link(_now: Any = None) -> None:
        async_update_link_issues(hass, entry)

    _check_link()
    entry.async_on_unload(
        async_track_time_interval(
            hass, _check_link, timedelta(minutes=LINK_CHECK_INTERVAL_MINUTES)
        )
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    data = hass.data.get(DOMAIN, {})
    instance_id = entry.data.get(CONF_INSTANCE_ID)
    if instance_id:
        data.get(DATA_SESSIONS, {}).pop(instance_id, None)
        data.get(DATA_NONCE_CACHES, {}).pop(instance_id, None)
    data.get(DATA_COORDINATORS, {}).pop(entry.entry_id, None)
    # Setup re-raises them; a disabled or removed entry shouldn't keep a stale one.
    async_clear_link_issues(hass, entry.entry_id)

    # The entry itself still counts, so a reload (rotate, extend, options)
    # doesn't pull the panel out from under the user; disabling it does.
    if not _panel_wanted(hass):
        async_unregister_panel(hass)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if not _panel_wanted(hass, entry.entry_id):
        async_unregister_panel(hass)


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload on any change; a new grant also narrows already-issued tokens."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Domain-level services; each acts on every configured entry."""

    async def _refresh(_call: ServiceCall) -> None:
        coords = hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {})
        for coord in coords.values():
            await coord.async_request_refresh()

    async def _rotate_secret(_call: ServiceCall) -> None:
        sessions = hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
        # Snapshot: updating an entry reloads it and replaces its session.
        for instance_id, session in list(sessions.items()):
            entry = hass.config_entries.async_get_entry(session["entry_id"])
            if entry is None:
                continue
            new_secret = secrets.token_hex(32)
            expires_at = new_link_expiry()
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_SECRET: new_secret,
                    CONF_LINK_EXPIRES_AT: expires_at,
                },
            )
            # Patch the live session so the old secret dies now, not on reload.
            session["secret"] = bytes.fromhex(new_secret)
            session[CONF_LINK_EXPIRES_AT] = expires_at
            # Never put the secret here: non-admins can read notifications.
            async_create_notification(
                hass,
                "The InkView shared secret was rotated; the previous one "
                "stopped working immediately. Open the InkView panel → "
                '"Connect to InkView" (admins only) to copy the new secret '
                "into your InkView server.",
                title="InkView secret rotated",
                notification_id=f"{DOMAIN}_secret_{instance_id}",
            )
            async_log_entry(hass, "InkView", "Rotated shared secret", DOMAIN)

    async def _revoke_all_tokens(_call: ServiceCall) -> None:
        sessions = hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
        for session in list(sessions.values()):  # see _rotate_secret
            entry = hass.config_entries.async_get_entry(session["entry_id"])
            if entry is None:
                continue
            new_kv = int(session.get("key_version", 1)) + 1
            session["key_version"] = new_kv
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_KEY_VERSION: new_kv},
            )
            async_log_entry(
                hass, "InkView", "Revoked all outstanding bearer tokens", DOMAIN
            )

    async def _extend_link(_call: ServiceCall) -> None:
        sessions = hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
        for session in list(sessions.values()):  # see _rotate_secret
            entry = hass.config_entries.async_get_entry(session["entry_id"])
            if entry is None:
                continue
            expires_at = new_link_expiry()
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_LINK_EXPIRES_AT: expires_at}
            )
            session[CONF_LINK_EXPIRES_AT] = expires_at
            async_update_link_issues(hass, entry)
            async_log_entry(
                hass, "InkView", "Extended the InkView link by one year", DOMAIN
            )

    # Credential-changing services are admin-only (a non-admin could DoS or
    # keep a lapsed link alive); automations/scripts can still call them.
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _refresh)
    async_register_admin_service(
        hass, DOMAIN, SERVICE_ROTATE_SECRET, _rotate_secret
    )
    async_register_admin_service(
        hass, DOMAIN, SERVICE_REVOKE_ALL_TOKENS, _revoke_all_tokens
    )
    async_register_admin_service(hass, DOMAIN, SERVICE_EXTEND_LINK, _extend_link)
