"""Coordinator for the total-energy sensor."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..const import DOMAIN, ENERGY_UPDATE_INTERVAL_MINUTES
from ..repairs import report_energy_state
from .energy_service import EnergyService

_LOGGER = logging.getLogger(__name__)


class InkViewEnergyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One per config entry."""

    def __init__(
        self, hass: HomeAssistant, allowed_entities: list[str] | None
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_energy",
            update_interval=timedelta(minutes=ENERGY_UPDATE_INTERVAL_MINUTES),
        )
        self._service = EnergyService(hass)
        # None = all sensors; an empty list = none.
        self._allowed = (
            None if allowed_entities is None else list(allowed_entities)
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = self._service.total(self._allowed)
        except Exception as e:
            raise UpdateFailed(f"energy sum failed: {e}") from e
        report_energy_state(self.hass, data.get("sensor_count", 0) > 0)
        return data
