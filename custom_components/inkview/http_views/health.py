"""GET /api/inkview/v1/health → {ok, energy_ready}. Unauthenticated.

Deliberately omits the version so scanners can't fingerprint vulnerable builds."""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from ..const import DATA_COORDINATORS, DOMAIN, URL_PREFIX

_LOGGER = logging.getLogger(__name__)


class InkViewHealthView(HomeAssistantView):
    url = f"{URL_PREFIX}/health"
    name = "api:inkview:health"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        coordinators = hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {})
        energy_ready = any(
            (c.data or {}).get("sensor_count", 0) > 0
            for c in coordinators.values()
        )
        return web.json_response({"ok": True, "energy_ready": energy_ready})
