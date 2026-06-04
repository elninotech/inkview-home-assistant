"""Total-energy figure derived from the user's chosen sensors.

InkView reads individual sensor states directly through the read-only REST
namespace. This service adds exactly one derived value: the live sum of the
selected energy sensors — anything reporting Wh / kWh / MWh — normalised to
kWh. No recorder statistics, no Energy-dashboard coupling, and no simulated
data: it's purely a sum of what the user picked, computed from the current
state machine.
"""
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

# Energy units that count toward the total, and their multiplier to kWh.
_ENERGY_UNIT_TO_KWH: dict[str, float] = {
    UnitOfEnergy.WATT_HOUR: 0.001,
    UnitOfEnergy.KILO_WATT_HOUR: 1.0,
    UnitOfEnergy.MEGA_WATT_HOUR: 1000.0,
}


def _energy_kwh(state: State | None) -> float | None:
    """Value of an energy sensor in kWh, or None if it isn't a usable
    numeric energy sensor (wrong domain, no/unknown unit, non-numeric)."""
    if state is None or not state.entity_id.startswith("sensor."):
        return None
    unit = state.attributes.get("unit_of_measurement")
    mult = _ENERGY_UNIT_TO_KWH.get(unit) if unit else None
    if mult is None:
        return None
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
    """Stateless; safe to instantiate per request. Reads the state machine
    directly, so all methods are sync and event-loop safe."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _own_entity_ids(self) -> set[str]:
        """Entity IDs that belong to InkView itself. These are never summed:
        sensor.inkview_total_energy reports its result in kWh, so feeding it
        back into the sum makes the total reference itself and run away
        exponentially. Matched via the entity registry's platform so it holds
        across renames and multiple config entries."""
        reg = er.async_get(self.hass)
        return {
            entry.entity_id
            for entry in reg.entities.values()
            if entry.platform == DOMAIN
        }

    def _candidate_ids(self, allowed: list[str] | None) -> list[str]:
        """Which sensors to consider. A non-empty allowlist is taken
        verbatim (de-duped, order preserved). An empty allowlist means
        'all sensors', so we scan every sensor.* entity. InkView's own
        entities are always dropped so the total can't feed back into itself."""
        own = self._own_entity_ids()
        if allowed:
            ids = list(dict.fromkeys(allowed))
        else:
            ids = [s.entity_id for s in self.hass.states.async_all("sensor")]
        return [eid for eid in ids if eid not in own]

    def total(self, allowed: list[str] | None) -> dict[str, Any]:
        """Sum the chosen energy sensors into a single kWh figure plus the
        per-sensor breakdown that fed it."""
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
