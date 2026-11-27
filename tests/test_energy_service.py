"""Tests for EnergyService."""
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.inkview.const import DOMAIN
from custom_components.inkview.energy.energy_service import EnergyService


def _meter(unit: str = "kWh") -> dict:
    return {"unit_of_measurement": unit, "state_class": "total_increasing"}


async def test_sums_and_normalises_units(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.kwh", "100", _meter())
    hass.states.async_set("sensor.wh", "1000", _meter("Wh"))
    hass.states.async_set("sensor.mwh", "2", _meter("MWh"))
    hass.states.async_set("sensor.text", "abc", _meter())
    hass.states.async_set("sensor.nounit", "5", {})

    result = EnergyService(hass).total(None)  # None == all renderable

    assert result["total_energy_kwh"] == pytest.approx(2101.0)
    assert result["sensor_count"] == 3


async def test_skips_energy_sensors_that_are_not_meters(hass: HomeAssistant) -> None:
    # Forecast.Solar-style: kWh but no state_class, i.e. a prediction, not a meter.
    hass.states.async_set("sensor.solar", "4356", _meter())
    hass.states.async_set(
        "sensor.forecast_today", "23", {"unit_of_measurement": "kWh"}
    )
    hass.states.async_set(
        "sensor.power",
        "800",
        {"unit_of_measurement": "kWh", "state_class": "measurement"},
    )

    result = EnergyService(hass).total(None)

    assert result["total_energy_kwh"] == pytest.approx(4356.0)
    assert [s["entity_id"] for s in result["sources"]] == ["sensor.solar"]


async def test_excludes_own_total_entity(hass: HomeAssistant) -> None:
    reg = er.async_get(hass)
    entry = reg.async_get_or_create(
        "sensor", DOMAIN, "total-1", suggested_object_id="inkview_total_energy"
    )
    hass.states.async_set("sensor.house", "100", _meter())
    hass.states.async_set(entry.entity_id, "999999", _meter())

    result = EnergyService(hass).total(None)

    assert result["total_energy_kwh"] == pytest.approx(100.0)
    assert result["sensor_count"] == 1
    assert entry.entity_id not in [s["entity_id"] for s in result["sources"]]


async def test_explicit_allowlist_restricts(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.a", "10", _meter())
    hass.states.async_set("sensor.b", "20", _meter())

    result = EnergyService(hass).total(["sensor.a"])

    assert result["total_energy_kwh"] == pytest.approx(10.0)
    assert result["sensor_count"] == 1


async def test_empty_allowlist_sums_nothing(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.a", "10", _meter())

    result = EnergyService(hass).total([])

    assert result["sensor_count"] == 0
    assert result["total_energy_kwh"] == pytest.approx(0.0)


async def test_own_entity_excluded_even_if_explicitly_allowed(hass: HomeAssistant) -> None:
    reg = er.async_get(hass)
    entry = reg.async_get_or_create(
        "sensor", DOMAIN, "total-2", suggested_object_id="inkview_total_energy"
    )
    hass.states.async_set(entry.entity_id, "999999", _meter())

    result = EnergyService(hass).total([entry.entity_id])

    assert result["sensor_count"] == 0
    assert result["total_energy_kwh"] == pytest.approx(0.0)
