"""GET /api/inkview/v1/states
→ {"sensors": [{entity_id, state, unit, friendly_name, last_updated}], "count": N}

Same filter and allowlist as GET /states/{entity_id}, so it never exposes more."""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from ..const import URL_PREFIX
from ._common import authenticate_bearer, effective_allowlist
from .states import _renderable

_LOGGER = logging.getLogger(__name__)


class InkViewStatesListView(HomeAssistantView):
    url = f"{URL_PREFIX}/states"
    name = "api:inkview:states-list"
    requires_auth = False  # custom bearer

    async def get(self, request: web.Request) -> web.Response:
        result = authenticate_bearer(request)
        if isinstance(result, web.Response):
            return result
        claims, session = result

        allowed = effective_allowlist(claims, session)
        hass = request.app["hass"]

        # None = scan every sensor.*; an empty set lists nothing.
        if allowed is not None:
            candidates = (hass.states.get(eid) for eid in sorted(allowed))
        else:
            candidates = hass.states.async_all("sensor")

        sensors: list[dict[str, Any]] = []
        for state in candidates:
            if not _renderable(state):
                continue
            attrs = state.attributes
            sensors.append(
                {
                    "entity_id": state.entity_id,
                    "state": state.state,
                    "unit": attrs.get("unit_of_measurement"),
                    "friendly_name": attrs.get("friendly_name"),
                    "last_updated": state.last_updated.isoformat()
                    if state.last_updated
                    else None,
                }
            )

        if "stats" in session:
            session["stats"].record_state_fetch()
        return web.json_response({"sensors": sensors, "count": len(sensors)})
