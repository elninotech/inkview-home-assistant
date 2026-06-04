"""SensorEntity layer (in-HA visualization).

A single derived sensor — `sensor.inkview_total_energy` — exposes the kWh
sum of the energy sensors the user selected (or all energy sensors, if the
allowlist is empty). The per-sensor breakdown that fed the total rides along
as the `contributing_sensors` attribute so the sidebar panel can render it
without extra entities.

State class is TOTAL (not TOTAL_INCREASING): the sum can fall if one of the
contributing sensors drops or goes unavailable, and TOTAL_INCREASING would
misread that as a meter reset."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, VERSION
from .energy.coordinator import InkViewEnergyCoordinator

_LOGGER = logging.getLogger(__name__)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title or "InkView",
        manufacturer="InkView",
        model="HA Integration",
        sw_version=VERSION,
        entry_type=None,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: InkViewEnergyCoordinator = hass.data[DOMAIN][DATA_COORDINATORS][
        entry.entry_id
    ]
    async_add_entities([InkViewTotalEnergySensor(coordinator, entry)])


class InkViewTotalEnergySensor(
    CoordinatorEntity[InkViewEnergyCoordinator], SensorEntity
):
    """kWh sum of the selected energy sensors."""

    _attr_has_entity_name = True
    _attr_name = "Total Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator: InkViewEnergyCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_total_energy"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        v = data.get("total_energy_kwh")
        return float(v) if isinstance(v, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        return {
            "sensor_count": data.get("sensor_count", 0),
            "computed_at": data.get("computed_at"),
            "contributing_sensors": [
                {
                    "entity_id": s.get("entity_id"),
                    "name": s.get("friendly_name"),
                    "kwh": s.get("kwh"),
                }
                for s in (data.get("sources") or [])
            ],
        }
