"""Per-period energy summary for the sidebar panel, from recorder long-term statistics.

Grouped like HA's Energy dashboard; without one, a flat list of granted meters.
Only granted meters are included; excluded dashboard meters are counted in `hidden`."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .energy_service import EnergyService, is_energy_meter

_LOGGER = logging.getLogger(__name__)

# Display order and sign in HA's consumption formula:
# import + solar + discharge - export - charge.
GROUPS: tuple[tuple[str, int], ...] = (
    ("solar", 1),
    ("grid_import", 1),
    ("grid_export", -1),
    ("battery_out", 1),
    ("battery_in", -1),
)

_KWH_UNITS = {"energy": UnitOfEnergy.KILO_WATT_HOUR}


def period_start(period: str, now: datetime) -> datetime:
    """Local-midnight start of the period containing `now`; weeks start Monday."""
    today = dt_util.as_local(now).date()
    if period == "week":
        first = today - timedelta(days=today.weekday())
    elif period == "month":
        first = today.replace(day=1)
    elif period == "year":
        first = date(today.year, 1, 1)
    else:
        first = today
    return dt_util.start_of_local_day(first)


def dashboard_meters(
    prefs: dict[str, Any] | None,
) -> tuple[dict[str, list[tuple[str, str | None]]], list[tuple[str, str | None]]]:
    """(groups, devices) of (statistic_id, name) pairs from Energy dashboard prefs.

    Handles legacy flow_from/flow_to grids and unified (HA 2026.x) grid sources."""
    groups: dict[str, list[tuple[str, str | None]]] = {k: [] for k, _ in GROUPS}
    seen: set[tuple[str, str]] = set()

    def add(key: str, stat_id: Any, name: Any = None) -> None:
        if not isinstance(stat_id, str) or not stat_id or (key, stat_id) in seen:
            return
        seen.add((key, stat_id))
        groups[key].append((stat_id, name if isinstance(name, str) else None))

    for src in (prefs or {}).get("energy_sources") or []:
        kind, name = src.get("type"), src.get("name")
        if kind == "grid":
            for flow in src.get("flow_from") or []:
                add("grid_import", flow.get("stat_energy_from"))
            for flow in src.get("flow_to") or []:
                add("grid_export", flow.get("stat_energy_to"))
            add("grid_import", src.get("stat_energy_from"), name)
            add("grid_export", src.get("stat_energy_to"), name)
        elif kind == "solar":
            add("solar", src.get("stat_energy_from"), name)
        elif kind == "battery":
            add("battery_out", src.get("stat_energy_from"), name)
            add("battery_in", src.get("stat_energy_to"), name)

    devices: list[tuple[str, str | None]] = []
    for dev in (prefs or {}).get("device_consumption") or []:
        stat_id = dev.get("stat_consumption")
        if isinstance(stat_id, str) and stat_id:
            name = dev.get("name")
            devices.append((stat_id, name if isinstance(name, str) else None))
    return groups, devices


async def _async_energy_prefs(hass: HomeAssistant) -> dict[str, Any] | None:
    if "energy" not in hass.config.components:
        return None
    from homeassistant.components.energy.data import async_get_manager

    manager = await async_get_manager(hass)
    return manager.data


async def _async_changes(
    hass: HomeAssistant, stat_ids: list[str], start: datetime, end: datetime
) -> dict[str, float | None]:
    """kWh change per statistic over the period; None where the recorder has no data."""
    if not stat_ids or "recorder" not in hass.config.components:
        return {sid: None for sid in stat_ids}
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import (
        statistic_during_period,
    )

    def _query() -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for sid in stat_ids:
            try:
                row = statistic_during_period(
                    hass, start, end, sid, {"change"}, _KWH_UNITS
                )
            except Exception:  # noqa: BLE001 — one bad meter mustn't sink all
                _LOGGER.debug("statistics query failed for %s", sid, exc_info=True)
                row = {}
            change = row.get("change")
            out[sid] = float(change) if isinstance(change, (int, float)) else None
        return out

    return await get_instance(hass).async_add_executor_job(_query)


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 3)


def _sum(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


async def async_energy_summary(
    hass: HomeAssistant,
    period: str,
    grant: set[str] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Energy per group for the period so far, limited to `grant` (None = all sensors)."""
    end = now or dt_util.utcnow()
    start = period_start(period, end)

    def allowed(stat_id: str) -> bool:
        return grant is None or stat_id in grant

    def label(stat_id: str, configured: str | None) -> str:
        if configured:
            return configured
        state = hass.states.get(stat_id)
        return (state and state.attributes.get("friendly_name")) or stat_id

    prefs = await _async_energy_prefs(hass)
    groups, devices = dashboard_meters(prefs)
    configured = [m for pairs in groups.values() for m in pairs] + devices
    hidden = sum(1 for sid, _ in configured if not allowed(sid))

    result: dict[str, Any] = {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "hidden": hidden,
    }

    if configured:
        groups = {k: [m for m in v if allowed(m[0])] for k, v in groups.items()}
        devices = [m for m in devices if allowed(m[0])]
        ids = list(
            dict.fromkeys(
                [sid for pairs in groups.values() for sid, _ in pairs]
                + [sid for sid, _ in devices]
            )
        )
        changes = await _async_changes(hass, ids, start, end)

        def rows(pairs: list[tuple[str, str | None]]) -> list[dict[str, Any]]:
            return [
                {"id": sid, "name": label(sid, name), "kwh": _round(changes.get(sid))}
                for sid, name in pairs
            ]

        out_groups = []
        consumption: float | None = 0.0
        for key, sign in GROUPS:
            if not groups[key]:
                continue
            values = [changes.get(sid) for sid, _ in groups[key]]
            total = _sum(values)
            out_groups.append(
                {"key": key, "kwh": _round(total), "sources": rows(groups[key])}
            )
            if consumption is not None and None not in values:
                consumption += sign * total
            else:
                consumption = None
        # A hidden meter, or one without statistics, would make the formula
        # silently undercount.
        if hidden or not any(g["key"] in ("solar", "grid_import") for g in out_groups):
            consumption = None
        result.update(
            source="energy_dashboard",
            groups=out_groups,
            consumption_kwh=_round(None if consumption is None else max(0.0, consumption)),
            devices=rows(devices),
            meters=[],
        )
        return result

    # No Energy dashboard: flat list of granted meters.
    service = EnergyService(hass)
    own = service.own_entity_ids()
    candidates = (
        [s.entity_id for s in hass.states.async_all("sensor")]
        if grant is None
        else sorted(grant)
    )
    meters = [
        eid
        for eid in candidates
        if eid not in own and is_energy_meter(hass.states.get(eid))
    ]
    changes = await _async_changes(hass, meters, start, end)
    result.update(
        source="sensors",
        groups=[],
        consumption_kwh=None,
        devices=[],
        meters=[
            {"id": eid, "name": label(eid, None), "kwh": _round(changes.get(eid))}
            for eid in meters
        ],
    )
    return result
