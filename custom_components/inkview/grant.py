"""The sensor grant — which entities InkView may read.

A grant is either "all renderable sensors" or an explicit list, and an
explicit list may be empty, meaning "read nothing". The two must never be
conflated, so "all" is carried as an explicit `all_sensors` flag everywhere
(config entry, session, bearer claims) instead of being inferred from an
empty `allowed_entities` list."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import CONF_ALL_SENSORS, CONF_ALLOWED_ENTITIES


def entry_grant(entry: ConfigEntry) -> list[str] | None:
    """The entry's current grant: None for all sensors, else the picked list
    (possibly empty). Options take precedence over the original data."""
    allowed = list(
        entry.options.get(
            CONF_ALLOWED_ENTITIES, entry.data.get(CONF_ALLOWED_ENTITIES, [])
        )
        or []
    )
    # Entries without the toggle predate it, when an empty list meant "all".
    all_sensors = bool(
        entry.options.get(
            CONF_ALL_SENSORS, entry.data.get(CONF_ALL_SENSORS, not allowed)
        )
    )
    return None if all_sensors else allowed


def grant_set(source: Mapping[str, Any]) -> set[str] | None:
    """Read a grant from a session or bearer claims: None for all sensors,
    else a strict set (possibly empty == deny all).

    Fails closed: only an explicit `all_sensors: true` grants everything. A
    bearer minted before the flag existed carries a bare `allowed_entities`
    list, and an empty one is treated as "read nothing" — never as "all"."""
    if source.get(CONF_ALL_SENSORS) is True:
        return None
    return {str(v) for v in (source.get(CONF_ALLOWED_ENTITIES) or [])}
