"""Energy summary logic; the recorder and Energy-dashboard prefs are patched out."""
from datetime import datetime
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.inkview.energy import summary
from custom_components.inkview.energy.summary import (
    async_energy_summary,
    dashboard_meters,
    period_start,
)

LEGACY_PREFS = {
    "energy_sources": [
        {
            "type": "grid",
            "flow_from": [{"stat_energy_from": "sensor.grid_in"}],
            "flow_to": [{"stat_energy_to": "sensor.grid_out"}],
        },
        {"type": "solar", "stat_energy_from": "sensor.solar"},
        {
            "type": "battery",
            "stat_energy_from": "sensor.bat_out",
            "stat_energy_to": "sensor.bat_in",
        },
        {"type": "gas", "stat_energy_from": "sensor.gas"},
    ],
    "device_consumption": [{"stat_consumption": "sensor.heat_pump", "name": "Heat pump"}],
}

CHANGES = {
    "sensor.grid_in": 6.0,
    "sensor.grid_out": 4.0,
    "sensor.solar": 15.0,
    "sensor.bat_out": 3.0,
    "sensor.bat_in": 5.0,
    "sensor.heat_pump": 2.5,
}


def _patched(prefs, changes=CHANGES):
    async def fake_changes(_hass, ids, _start, _end):
        return {sid: changes.get(sid) for sid in ids}

    async def fake_prefs(_hass):
        return prefs

    return (
        patch.object(summary, "_async_energy_prefs", fake_prefs),
        patch.object(summary, "_async_changes", fake_changes),
    )


async def _summary(hass, prefs, grant=None, changes=CHANGES, period="today"):
    p1, p2 = _patched(prefs, changes)
    with p1, p2:
        return await async_energy_summary(hass, period, grant)


def test_legacy_and_unified_grid_formats_both_parse():
    unified = {
        "energy_sources": [
            {
                "type": "grid",
                "stat_energy_from": "sensor.grid_in",
                "stat_energy_to": None,
                "name": "Main meter",
            },
            {"type": "grid", "stat_energy_from": None, "stat_energy_to": "sensor.grid_out"},
        ]
    }
    groups, _ = dashboard_meters(unified)
    assert groups["grid_import"] == [("sensor.grid_in", "Main meter")]
    assert groups["grid_export"] == [("sensor.grid_out", None)]

    groups, devices = dashboard_meters(LEGACY_PREFS)
    assert groups["grid_import"] == [("sensor.grid_in", None)]
    assert groups["solar"] == [("sensor.solar", None)]
    assert devices == [("sensor.heat_pump", "Heat pump")]


async def test_groups_and_home_consumption(hass: HomeAssistant) -> None:
    out = await _summary(hass, LEGACY_PREFS)

    assert out["source"] == "energy_dashboard"
    assert [g["key"] for g in out["groups"]] == [
        "solar",
        "grid_import",
        "grid_export",
        "battery_out",
        "battery_in",
    ]
    # import + solar + discharge - export - charge
    assert out["consumption_kwh"] == pytest.approx(6 + 15 + 3 - 4 - 5)
    assert out["devices"] == [
        {"id": "sensor.heat_pump", "name": "Heat pump", "kwh": 2.5}
    ]
    assert out["hidden"] == 0


async def test_meters_outside_the_grant_are_hidden(hass: HomeAssistant) -> None:
    out = await _summary(hass, LEGACY_PREFS, grant={"sensor.solar"})

    assert [g["key"] for g in out["groups"]] == ["solar"]
    assert out["hidden"] == 5
    # Would undercount with meters hidden.
    assert out["consumption_kwh"] is None


async def test_missing_statistics_are_none_not_zero(hass: HomeAssistant) -> None:
    out = await _summary(hass, LEGACY_PREFS, changes={"sensor.solar": 15.0})

    solar = next(g for g in out["groups"] if g["key"] == "solar")
    grid = next(g for g in out["groups"] if g["key"] == "grid_import")
    assert solar["kwh"] == 15.0
    assert grid["kwh"] is None
    assert grid["sources"][0]["kwh"] is None
    assert out["consumption_kwh"] is None


async def test_without_energy_dashboard_lists_granted_meters(
    hass: HomeAssistant,
) -> None:
    meter = {"unit_of_measurement": "kWh", "state_class": "total_increasing"}
    hass.states.async_set("sensor.solar", "4356", {**meter, "friendly_name": "Solar"})
    hass.states.async_set("sensor.forecast", "23", {"unit_of_measurement": "kWh"})

    out = await _summary(hass, None, changes={"sensor.solar": 18.4})

    assert out["source"] == "sensors"
    assert out["meters"] == [{"id": "sensor.solar", "name": "Solar", "kwh": 18.4}]


async def test_empty_grant_shows_nothing(hass: HomeAssistant) -> None:
    out = await _summary(hass, LEGACY_PREFS, grant=set())

    assert out["groups"] == []
    assert out["devices"] == []
    assert out["hidden"] == 6


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("today", datetime(2026, 10, 15)),
        ("week", datetime(2026, 10, 12)),  # Monday
        ("month", datetime(2026, 10, 1)),
        ("year", datetime(2026, 1, 1)),
    ],
)
async def test_period_starts_at_local_midnight(
    hass: HomeAssistant, period, expected
) -> None:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    # 01:30 local on the 15th is still the 14th in UTC.
    now = dt_util.as_utc(
        datetime(2026, 10, 15, 1, 30, tzinfo=dt_util.get_time_zone("Europe/Amsterdam"))
    )
    start = period_start(period, now)
    assert start.replace(tzinfo=None) == expected
    assert start.tzinfo is not None
