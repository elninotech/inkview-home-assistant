"""Bearer-authenticated total-energy endpoint.

GET /api/inkview/v1/energy/totals

Returns the kWh sum of the energy sensors this token is allowed to see
(empty allowlist == all renderable sensors), plus the per-sensor breakdown.
Read-only — never mutates HA."""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from homeassistant.util import dt as dt_util

from ..const import URL_PREFIX
from ..energy.energy_service import EnergyService
from ._common import authenticate_bearer, effective_allowlist

_LOGGER = logging.getLogger(__name__)


class InkViewEnergyTotalsView(HomeAssistantView):
    url = f"{URL_PREFIX}/energy/totals"
    name = "api:inkview:energy-totals"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        result = authenticate_bearer(request)
        if isinstance(result, web.Response):
            return result
        claims, session = result

        # None == all renderable sensors; a set (possibly empty) == strict
        # allowlist. EnergyService treats an empty list as "all", so the
        # deny-all case (empty set) is short-circuited to a zero total here.
        allowed = effective_allowlist(claims, session)
        hass = request.app["hass"]
        try:
            if allowed is not None and not allowed:
                payload = {
                    "total_energy_kwh": 0.0,
                    "sensor_count": 0,
                    "sources": [],
                    "computed_at": dt_util.utcnow().isoformat(),
                }
            else:
                payload = EnergyService(hass).total(
                    None if allowed is None else sorted(allowed)
                )
        except Exception:  # noqa: BLE001 — never leak internals to the caller
            _LOGGER.exception("energy total failed")
            return web.json_response({"error": "energy_unavailable"}, status=503)

        if "stats" in session:
            session["stats"].record_state_fetch()
        return web.json_response(payload)
