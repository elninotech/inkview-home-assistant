"""Unauthenticated reachability check.

GET /api/inkview/v1/health → { ok, version, energy_ready }

Deliberately reveals only what InkView already learns from finding any
authenticated endpoint at this base URL: this host runs the integration.
The integration version is intentionally NOT exposed here — version strings
on an unauthenticated endpoint just hand a scanner a way to fingerprint a
vulnerable build. Authenticated callers get it from the manifest."""
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
        # "energy_ready" now means: at least one configured session is
        # summing one or more energy sensors into a total. No Energy-dashboard
        # dependency.
        coordinators = hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {})
        energy_ready = any(
            (c.data or {}).get("sensor_count", 0) > 0
            for c in coordinators.values()
        )
        return web.json_response({"ok": True, "energy_ready": energy_ready})
