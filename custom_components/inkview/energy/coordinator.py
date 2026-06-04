"""DataUpdateCoordinator powering the in-HA total-energy sensor.

Recomputes the sum of the chosen energy sensors once every few minutes and
surfaces failures as UpdateFailed so HA's UI shows the integration as
degraded without crashing."""
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
    """One coordinator per config entry; sums that entry's chosen sensors."""

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
        self._allowed = list(allowed_entities or [])

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = self._service.total(self._allowed)
        except Exception as e:
            raise UpdateFailed(f"energy sum failed: {e}") from e
        # Nudge the user via Repairs if nothing summable was found.
        report_energy_state(self.hass, data.get("sensor_count", 0) > 0)
        return data
