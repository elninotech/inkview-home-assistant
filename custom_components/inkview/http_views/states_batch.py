"""Bulk states endpoint — one round-trip for many entities.

POST /api/inkview/v1/states/batch
Body: {"entity_ids": ["sensor.a", "sensor.b", ...]}
Resp: {"states": {"sensor.a": {state, unit, ...}, "sensor.b": {error: ...}, ...}}

Per-entity errors are inlined into the response so the caller gets a
useful answer for as many ids as possible from a single call."""
from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from ..const import MAX_BATCH_BODY_BYTES, MAX_BATCH_ENTITY_IDS, URL_PREFIX
from ._common import authenticate_bearer, effective_allowlist
from .states import _renderable

_LOGGER = logging.getLogger(__name__)


class InkViewBatchStateView(HomeAssistantView):
    url = f"{URL_PREFIX}/states/batch"
    name = "api:inkview:states-batch"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        result = authenticate_bearer(request)
        if isinstance(result, web.Response):
            return result
        claims, session = result

        body = await request.content.read(MAX_BATCH_BODY_BYTES + 1)
        if len(body) > MAX_BATCH_BODY_BYTES:
            return web.json_response({"error": "payload_too_large"}, status=413)
        try:
            payload: Any = json.loads(body)
        except (ValueError, TypeError):
            return web.json_response({"error": "malformed_json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "malformed_json"}, status=400)

        ids = payload.get("entity_ids")
        if not isinstance(ids, list) or not ids:
            return web.json_response({"error": "bad_entity_ids"}, status=400)
        if len(ids) > MAX_BATCH_ENTITY_IDS:
            return web.json_response({"error": "too_many_entities"}, status=400)
        if not all(isinstance(x, str) and "." in x for x in ids):
            return web.json_response({"error": "bad_entity_ids"}, status=400)

        # None = all renderable sensors; a set (possibly empty) = strict list.
        allowed = effective_allowlist(claims, session)
        hass = request.app["hass"]
        out: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        for eid in ids:
            if eid in seen:
                continue
            seen.add(eid)
            if allowed is not None and eid not in allowed:
                out[eid] = {"error": "entity_not_allowed"}
                continue
            state = hass.states.get(eid)
            if not _renderable(state):
                out[eid] = {"error": "entity_unavailable"}
                continue
            attrs = state.attributes
            out[eid] = {
                "state": state.state,
                "unit": attrs.get("unit_of_measurement"),
                "friendly_name": attrs.get("friendly_name"),
                "last_updated": state.last_updated.isoformat()
                if state.last_updated
                else None,
            }
        if "stats" in session:
            session["stats"].record_state_fetch()
        return web.json_response({"states": out})
