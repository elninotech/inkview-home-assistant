"""GET /api/inkview/v1/energy/totals — kWh sum of granted energy meters plus breakdown."""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

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

        allowed = effective_allowlist(claims, session)
        hass = request.app["hass"]
        try:
            payload = EnergyService(hass).total(
                None if allowed is None else sorted(allowed)
            )
        except Exception:  # noqa: BLE001 — don't leak internals
            _LOGGER.exception("energy total failed")
            return web.json_response({"error": "energy_unavailable"}, status=503)

        if "stats" in session:
            session["stats"].record_state_fetch()
        return web.json_response(payload)
