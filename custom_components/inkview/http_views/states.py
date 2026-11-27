"""GET /api/inkview/v1/states/{entity_id} — single sensor state."""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import State

from ..const import URL_PREFIX
from ._common import authenticate_bearer, effective_allowlist

_LOGGER = logging.getLogger(__name__)


def _renderable(state: State | None) -> bool:
    """Numeric sensor.* with a unit; mirrors the InkView server's is_renderable_sensor."""
    if state is None:
        return False
    if not state.entity_id.startswith("sensor."):
        return False
    unit = state.attributes.get("unit_of_measurement")
    if not unit:
        return False
    try:
        float(state.state)
    except (TypeError, ValueError):
        return False
    return True


class InkViewStateView(HomeAssistantView):
    url = f"{URL_PREFIX}/states/{{entity_id}}"
    name = "api:inkview:state"
    requires_auth = False  # custom bearer

    async def get(self, request: web.Request, entity_id: str) -> web.Response:
        result = authenticate_bearer(request)
        if isinstance(result, web.Response):
            return result
        claims, session = result

        allowed = effective_allowlist(claims, session)
        if allowed is not None and entity_id not in allowed:
            return web.json_response({"error": "entity_not_allowed"}, status=403)

        hass = request.app["hass"]
        state = hass.states.get(entity_id)
        if not _renderable(state):
            return web.json_response({"error": "entity_unavailable"}, status=404)
        assert state is not None  # narrowed by _renderable

        if "stats" in session:
            session["stats"].record_state_fetch()

        attrs = state.attributes
        return web.json_response(
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
