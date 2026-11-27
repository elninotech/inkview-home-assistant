"""Sensor grant: which entities InkView may read. "All" is an explicit
`all_sensors` flag, never inferred from an empty list ("read nothing")."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import CONF_ALL_SENSORS, CONF_ALLOWED_ENTITIES


def entry_grant(entry: ConfigEntry) -> list[str] | None:
    """None for all sensors, else the picked list. Options override data."""
    allowed = list(
        entry.options.get(
            CONF_ALLOWED_ENTITIES, entry.data.get(CONF_ALLOWED_ENTITIES, [])
        )
        or []
    )
    # Legacy entries without the flag: an empty list meant "all".
    all_sensors = bool(
        entry.options.get(
            CONF_ALL_SENSORS, entry.data.get(CONF_ALL_SENSORS, not allowed)
        )
    )
    return None if all_sensors else allowed


def grant_set(source: Mapping[str, Any]) -> set[str] | None:
    """None for all sensors, else the allowed set. Fails closed: only an
    explicit all_sensors grants everything."""
    if source.get(CONF_ALL_SENSORS) is True:
        return None
    return {str(v) for v in (source.get(CONF_ALLOWED_ENTITIES) or [])}


def combined_grant(sources: Iterable[Mapping[str, Any]]) -> set[str] | None:
    """Union of sessions' grants (for the panel); None if any grants all."""
    out: set[str] = set()
    for source in sources:
        grant = grant_set(source)
        if grant is None:
            return None
        out |= grant
    return out
