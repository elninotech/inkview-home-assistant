"""Link (instance_id + secret) expiry: the real access limit, since bearers
are re-minted on every refresh. Enforced at mint time and on every request."""
from __future__ import annotations

import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_LINK_EXPIRES_AT,
    DOMAIN,
    ISSUE_LINK_EXPIRED,
    ISSUE_LINK_EXPIRING,
    LINK_LIFETIME_SECONDS,
    LINK_WARN_SECONDS,
)


def new_link_expiry(now: float | None = None) -> int:
    return int((time.time() if now is None else now) + LINK_LIFETIME_SECONDS)


def entry_link_expiry(entry: ConfigEntry) -> int | None:
    value = entry.data.get(CONF_LINK_EXPIRES_AT)
    return int(value) if isinstance(value, (int, float)) else None


def link_expired(session: dict, now: float | None = None) -> bool:
    """Fails closed: a session without an expiry counts as expired."""
    expires_at = session.get(CONF_LINK_EXPIRES_AT)
    if not isinstance(expires_at, (int, float)):
        return True
    return (time.time() if now is None else now) >= expires_at


def _issue_id(kind: str, entry_id: str) -> str:
    return f"{kind}_{entry_id}"


def async_update_link_issues(
    hass: HomeAssistant, entry: ConfigEntry, now: float | None = None
) -> None:
    """Raise or clear the Repairs issue for an expiring/expired link."""
    expires_at = entry_link_expiry(entry)
    remaining = (
        None
        if expires_at is None
        else expires_at - (time.time() if now is None else now)
    )
    expiring_id = _issue_id(ISSUE_LINK_EXPIRING, entry.entry_id)
    expired_id = _issue_id(ISSUE_LINK_EXPIRED, entry.entry_id)
    placeholders = {"name": entry.title or "InkView"}

    if remaining is not None and remaining <= 0:
        ir.async_delete_issue(hass, DOMAIN, expiring_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            expired_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_LINK_EXPIRED,
            translation_placeholders=placeholders,
            learn_more_url="/inkview",
        )
        return

    ir.async_delete_issue(hass, DOMAIN, expired_id)
    if remaining is not None and remaining <= LINK_WARN_SECONDS:
        days = max(1, int(remaining // 86400))
        ir.async_create_issue(
            hass,
            DOMAIN,
            expiring_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_LINK_EXPIRING,
            translation_placeholders={**placeholders, "days": str(days)},
            learn_more_url="/inkview",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, expiring_id)


def async_clear_link_issues(hass: HomeAssistant, entry_id: str) -> None:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(ISSUE_LINK_EXPIRING, entry_id))
    ir.async_delete_issue(hass, DOMAIN, _issue_id(ISSUE_LINK_EXPIRED, entry_id))
