"""Tests for EnergyService — unit normalisation, allowlist, and the
self-reference guard that stops the total from feeding back into itself.
"""
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.inkview.const import DOMAIN
from custom_components.inkview.energy.energy_service import EnergyService


async def test_sums_and_normalises_units(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.kwh", "100", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.wh", "1000", {"unit_of_measurement": "Wh"})   # 1 kWh
    hass.states.async_set("sensor.mwh", "2", {"unit_of_measurement": "MWh"})    # 2000 kWh
    hass.states.async_set("sensor.text", "abc", {"unit_of_measurement": "kWh"})  # non-numeric
    hass.states.async_set("sensor.nounit", "5", {})                              # no unit

    result = EnergyService(hass).total([])  # empty allowlist == all renderable

    assert result["total_energy_kwh"] == pytest.approx(2101.0)
    assert result["sensor_count"] == 3


async def test_excludes_own_total_entity(hass: HomeAssistant) -> None:
    # Register an entity that belongs to InkView itself.
    reg = er.async_get(hass)
    entry = reg.async_get_or_create(
        "sensor", DOMAIN, "total-1", suggested_object_id="inkview_total_energy"
    )
    hass.states.async_set("sensor.house", "100", {"unit_of_measurement": "kWh"})
    hass.states.async_set(entry.entity_id, "999999", {"unit_of_measurement": "kWh"})

    result = EnergyService(hass).total([])

    # The InkView total must not count itself, or it runs away exponentially.
    assert result["total_energy_kwh"] == pytest.approx(100.0)
    assert result["sensor_count"] == 1
    assert entry.entity_id not in [s["entity_id"] for s in result["sources"]]


async def test_explicit_allowlist_restricts(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.a", "10", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.b", "20", {"unit_of_measurement": "kWh"})

    result = EnergyService(hass).total(["sensor.a"])

    assert result["total_energy_kwh"] == pytest.approx(10.0)
    assert result["sensor_count"] == 1


async def test_own_entity_excluded_even_if_explicitly_allowed(hass: HomeAssistant) -> None:
    # Even a token that names the InkView total must not feed it back in.
    reg = er.async_get(hass)
    entry = reg.async_get_or_create(
        "sensor", DOMAIN, "total-2", suggested_object_id="inkview_total_energy"
    )
    hass.states.async_set(entry.entity_id, "999999", {"unit_of_measurement": "kWh"})

    result = EnergyService(hass).total([entry.entity_id])

    assert result["sensor_count"] == 0
    assert result["total_energy_kwh"] == pytest.approx(0.0)
