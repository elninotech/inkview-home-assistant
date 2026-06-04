"""InkView integration entry point."""
from __future__ import annotations

import logging
import secrets
from typing import Any

from homeassistant.components.logbook import async_log_entry
from homeassistant.components.persistent_notification import (
    async_create as async_create_notification,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .const import (
    CONF_ALLOWED_ENTITIES,
    CONF_INSTANCE_ID,
    CONF_KEY_VERSION,
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
    SERVICE_REFRESH,
    SERVICE_REVOKE_ALL_TOKENS,
    SERVICE_ROTATE_SECRET,
)
from .auth.stats import SessionStats
from .energy.coordinator import InkViewEnergyCoordinator
from .http_views import register_views
from .panel import async_register_panel, async_unregister_panel
from .ws_api import async_register_ws

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# InkView is configured via the UI (config flow) only — it has no YAML config.
# Declaring this satisfies hassfest and rejects any stray YAML under `inkview:`.
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
    """Sidebar panel is opt-out, edited via options."""
    if CONF_SHOW_SIDEBAR_PANEL in entry.options:
        return bool(entry.options[CONF_SHOW_SIDEBAR_PANEL])
    return bool(entry.data.get(CONF_SHOW_SIDEBAR_PANEL, True))


def _any_other_entry_wants_panel(
    hass: HomeAssistant, exclude_entry_id: str
) -> bool:
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == exclude_entry_id:
            continue
        if _panel_enabled(other):
            return True
    return False


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

    instance_id = entry.data[CONF_INSTANCE_ID]
    secret = bytes.fromhex(entry.data[CONF_SECRET])
    # Options take precedence over original data for things the user can edit
    # post-setup (the allowed-entities list).
    allowed: list[str] = list(
        entry.options.get(
            CONF_ALLOWED_ENTITIES,
            entry.data.get(CONF_ALLOWED_ENTITIES, []),
        )
    )
    key_version = int(entry.data.get(CONF_KEY_VERSION, 1))

    data[DATA_SESSIONS][instance_id] = {
        "entry_id": entry.entry_id,
        "secret": secret,
        "allowed_entities": allowed,
        "key_version": key_version,
        "stats": SessionStats(),
    }

    coordinator = InkViewEnergyCoordinator(hass, allowed)
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

    if not _any_other_entry_wants_panel(hass, entry.entry_id):
        async_unregister_panel(hass)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Trigger an entry reload when options change so the new
    allowed_entities take effect on the next token issuance."""
    await hass.config_entries.async_reload(entry.entry_id)


# --- Services --------------------------------------------------------------


def _register_services(hass: HomeAssistant) -> None:
    """Domain-level services. Acts across all configured entries; per-entry
    targeting via service data isn't critical because most users will only
    ever have one InkView session."""

    async def _refresh(_call: ServiceCall) -> None:
        coords = hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {})
        for coord in coords.values():
            await coord.async_request_refresh()

    async def _rotate_secret(_call: ServiceCall) -> None:
        sessions = hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
        for instance_id, session in sessions.items():
            entry = hass.config_entries.async_get_entry(session["entry_id"])
            if entry is None:
                continue
            new_secret = secrets.token_hex(32)
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_SECRET: new_secret},
            )
            # Live session must pick up the new secret without a full reload;
            # outstanding bearers (signed with old secret) stop working
            # immediately because the verify step is keyed on session["secret"].
            session["secret"] = bytes.fromhex(new_secret)
            # New mints start from key_version 1 of the new secret.
            session["key_version"] = 1
            # Never put the secret in a persistent notification: those are
            # global (every user, admin or not, can read them). The new
            # secret is retrievable only through the admin-gated
            # `inkview/credentials` WS command behind the panel's
            # "Connect to InkView" card.
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
        for session in sessions.values():
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

    # `refresh` is harmless (recompute only) and stays callable by any user.
    # `rotate_secret` and `revoke_all_tokens` change/expose the credential and
    # invalidate access, so they are admin-only — otherwise a non-admin could
    # rotate the secret (DoS) or revoke every token. async_register_admin_service
    # rejects non-admin callers with Unauthorized while still allowing internal
    # (user-less) calls from automations/scripts.
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _refresh)
    async_register_admin_service(
        hass, DOMAIN, SERVICE_ROTATE_SECRET, _rotate_secret
    )
    async_register_admin_service(
        hass, DOMAIN, SERVICE_REVOKE_ALL_TOKENS, _revoke_all_tokens
    )
