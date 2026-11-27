"""Live kWh sum of the chosen energy meters (Wh/kWh/MWh, total/total_increasing).

Forecasts and other energy sensors without a meter state class are skipped."""
from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_METER_STATE_CLASSES = {"total", "total_increasing"}

# Multiplier to kWh.
_ENERGY_UNIT_TO_KWH: dict[str, float] = {
    UnitOfEnergy.WATT_HOUR: 0.001,
    UnitOfEnergy.KILO_WATT_HOUR: 1.0,
    UnitOfEnergy.MEGA_WATT_HOUR: 1000.0,
}


def is_energy_meter(state: State | None) -> bool:
    return (
        state is not None
        and state.entity_id.startswith("sensor.")
        and state.attributes.get("unit_of_measurement") in _ENERGY_UNIT_TO_KWH
        and state.attributes.get("state_class") in _METER_STATE_CLASSES
    )


def _energy_kwh(state: State | None) -> float | None:
    """kWh value, or None if not a meter or not a finite number."""
    if state is None or not is_energy_meter(state):
        return None
    mult = _ENERGY_UNIT_TO_KWH[state.attributes["unit_of_measurement"]]
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value * mult


def _round_kwh(v: float) -> float:
    return round(v, 3)


class EnergyService:
    """Stateless and sync; safe to instantiate per request."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def own_entity_ids(self) -> set[str]:
        """InkView's own entities, never summed: the kWh total would feed back into itself.

        Matched by registry platform so it survives renames and multiple entries."""
        reg = er.async_get(self.hass)
        return {
            entry.entity_id
            for entry in reg.entities.values()
            if entry.platform == DOMAIN
        }

    def _candidate_ids(self, allowed: list[str] | None) -> list[str]:
        """De-duped allowlist (None = every sensor.*), minus InkView's own entities."""
        own = self.own_entity_ids()
        if allowed is not None:
            ids = list(dict.fromkeys(allowed))
        else:
            ids = [s.entity_id for s in self.hass.states.async_all("sensor")]
        return [eid for eid in ids if eid not in own]

    def total(self, allowed: list[str] | None) -> dict[str, Any]:
        """kWh total plus per-sensor breakdown."""
        contributors: list[dict[str, Any]] = []
        total_kwh = 0.0

        for eid in self._candidate_ids(allowed):
            state = self.hass.states.get(eid)
            kwh = _energy_kwh(state)
            if kwh is None:
                continue
            assert state is not None  # narrowed by _energy_kwh
            total_kwh += kwh
            contributors.append(
                {
                    "entity_id": eid,
                    "friendly_name": state.attributes.get("friendly_name") or eid,
                    "value": float(state.state),
                    "unit": state.attributes.get("unit_of_measurement"),
                    "kwh": _round_kwh(kwh),
                }
            )

        return {
            "total_energy_kwh": _round_kwh(total_kwh),
            "sensor_count": len(contributors),
            "sources": contributors,
            "computed_at": dt_util.utcnow().isoformat(),
        }
