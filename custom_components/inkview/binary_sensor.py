"""Connection health binary_sensor for the InkView session.

`binary_sensor.inkview_connected` is `on` whenever InkView has successfully
exercised the auth or read surface in the last CONNECTED_THRESHOLD_SECONDS.
Attributes expose the underlying counters so users can build automations
like "alert me if InkView hasn't synced for 30 min." """
from __future__ import annotations

import time
from datetime import datetime, timezone

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta

from .const import (
    CONF_INSTANCE_ID,
    CONNECTED_THRESHOLD_SECONDS,
    DATA_SESSIONS,
    DOMAIN,
    TOKEN_SCOPE,
    VERSION,
)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title or "InkView",
        manufacturer="InkView",
        model="HA Integration",
        sw_version=VERSION,
    )


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([InkViewConnectedSensor(hass, entry)])


class InkViewConnectedSensor(BinarySensorEntity):
    """Polled every 30 s; reads the session's SessionStats snapshot."""

    _attr_has_entity_name = True
    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._instance_id = entry.data[CONF_INSTANCE_ID]
        self._attr_unique_id = f"{entry.entry_id}_connected"
        self._attr_device_info = _device_info(entry)
        self._snapshot: dict = {}

    async def async_added_to_hass(self) -> None:
        # Refresh once a minute. We don't need finer granularity than that
        # for a "has InkView talked to us recently?" indicator.
        self.async_on_remove(
            async_track_time_interval(
                self._hass, self._async_tick, timedelta(seconds=30)
            )
        )
        self._refresh()

    @callback
    def _async_tick(self, _now) -> None:
        self._refresh()
        self.async_write_ha_state()

    def _refresh(self) -> None:
        sessions = self._hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
        session = sessions.get(self._instance_id)
        if session is None or "stats" not in session:
            self._snapshot = {}
            return
        self._snapshot = session["stats"].snapshot()

    @property
    def is_on(self) -> bool:
        snap = self._snapshot
        if not snap:
            return False
        # "Connected" if either the token mint or the data fetch happened
        # within the threshold. Either signal counts as InkView being alive.
        candidates = [
            snap.get("last_token_minted_at"),
            snap.get("last_state_fetch_at"),
        ]
        latest = max((c for c in candidates if c is not None), default=None)
        if latest is None:
            return False
        return (time.time() - latest) < CONNECTED_THRESHOLD_SECONDS

    @property
    def extra_state_attributes(self) -> dict:
        snap = self._snapshot
        return {
            "token_scope": TOKEN_SCOPE,
            "last_token_minted_at": _iso(snap.get("last_token_minted_at")),
            "last_token_expires_at": _iso(snap.get("last_token_expires_at")),
            "last_state_fetch_at": _iso(snap.get("last_state_fetch_at")),
            "last_failed_auth_at": _iso(snap.get("last_failed_auth_at")),
            "tokens_issued_24h": snap.get("tokens_issued_24h", 0),
            "failed_auth_24h": snap.get("failed_auth_24h", 0),
        }
