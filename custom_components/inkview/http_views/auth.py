"""Client-credentials token endpoint.

Why HMAC rather than a bearer here: this endpoint *issues* bearers, so it
can't require one of its own. HMAC over (instance_id, ts, nonce) gives us
replay protection without ever putting the shared secret on the wire."""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from homeassistant.components.logbook import async_log_entry

from ..auth.bearer import mint, verify_hmac
from ..const import (
    DATA_NONCE_CACHES,
    DATA_SESSIONS,
    DEFAULT_TOKEN_TTL_SECONDS,
    DOMAIN,
    HMAC_NONCE_CACHE_SIZE,
    HMAC_NONCE_TTL_SECONDS,
    HMAC_TIMESTAMP_WINDOW_SECONDS,
    MAX_AUTH_BODY_BYTES,
    TOKEN_SCOPE,
    URL_PREFIX,
)

_LOGGER = logging.getLogger(__name__)


def _register_nonce(cache: "OrderedDict[str, float]", nonce: str) -> bool:
    """Return True if the nonce is fresh; False if a replay. Side effect:
    evicts expired and over-cap entries on every call (O(k) where k is the
    number of expired entries — amortised O(1))."""
    now = time.monotonic()
    while cache:
        _oldest, expires_at = next(iter(cache.items()))
        if expires_at <= now:
            cache.popitem(last=False)
        else:
            break
    if nonce in cache:
        return False
    while len(cache) >= HMAC_NONCE_CACHE_SIZE:
        cache.popitem(last=False)
    cache[nonce] = now + HMAC_NONCE_TTL_SECONDS
    return True


class InkViewAuthTokenView(HomeAssistantView):
    """POST /api/inkview/v1/auth/token"""

    url = f"{URL_PREFIX}/auth/token"
    name = "api:inkview:auth-token"
    requires_auth = False  # uses HMAC; see module docstring

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        sessions = hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
        nonce_caches: dict[str, OrderedDict[str, float]] = hass.data.setdefault(
            DOMAIN, {}
        ).setdefault(DATA_NONCE_CACHES, {})

        # Read with a hard upper bound to defend against accidental DoS.
        body = await request.content.read(MAX_AUTH_BODY_BYTES + 1)
        if len(body) > MAX_AUTH_BODY_BYTES:
            return web.json_response({"error": "payload_too_large"}, status=413)

        try:
            data: Any = json.loads(body)
        except (ValueError, TypeError):
            return web.json_response({"error": "malformed_json"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "malformed_json"}, status=400)

        instance_id = data.get("instance_id")
        ts = data.get("ts")
        nonce = data.get("nonce")
        sig = data.get("sig")

        if not all(isinstance(x, str) for x in (instance_id, ts, nonce, sig)):
            return web.json_response({"error": "bad_request"}, status=400)
        if not (8 <= len(nonce) <= 64):
            return web.json_response({"error": "bad_nonce"}, status=400)
        if len(sig) != 64:
            return web.json_response({"error": "bad_sig_format"}, status=400)

        try:
            ts_int = int(ts)
        except (ValueError, TypeError):
            return web.json_response({"error": "bad_timestamp"}, status=400)
        if abs(int(time.time()) - ts_int) > HMAC_TIMESTAMP_WINDOW_SECONDS:
            return web.json_response({"error": "timestamp_skew"}, status=401)

        session = sessions.get(instance_id)
        if session is None:
            # 401 not 404: don't leak which instance_ids exist.
            _LOGGER.debug("auth: unknown instance_id")
            return web.json_response({"error": "unauthorized"}, status=401)

        secret: bytes = session["secret"]
        # Canonical signed payload is just the instance_id bytes. Keeps the
        # signing contract independent of JSON ordering / whitespace.
        if not verify_hmac(secret, instance_id.encode("ascii"), ts, nonce, sig):
            if "stats" in session:
                session["stats"].record_failed_auth()
            _LOGGER.debug("auth: bad signature for instance %s", instance_id)
            return web.json_response({"error": "unauthorized"}, status=401)

        cache = nonce_caches.setdefault(instance_id, OrderedDict())
        if not _register_nonce(cache, nonce):
            if "stats" in session:
                session["stats"].record_failed_auth()
            return web.json_response({"error": "replay"}, status=401)

        allowed_entities: list[str] = list(session.get("allowed_entities") or [])
        key_version = int(session.get("key_version", 1))
        # scope="read" is advisory metadata — the token only ever works
        # against InkView's read-only endpoints, which never mutate HA.
        token, exp = mint(
            secret,
            sub=instance_id,
            key_version=key_version,
            ttl_seconds=DEFAULT_TOKEN_TTL_SECONDS,
            extra_claims={
                "allowed_entities": allowed_entities,
                "scope": TOKEN_SCOPE,
            },
        )
        if "stats" in session:
            session["stats"].record_token_issued(exp)
        async_log_entry(
            hass,
            "InkView",
            "Issued a read-only bearer token (valid 1 year)",
            DOMAIN,
        )
        return web.json_response(
            {
                "access_token": token,
                "token_type": "Bearer",
                "scope": TOKEN_SCOPE,
                "expires_at": exp,
                "expires_in": DEFAULT_TOKEN_TTL_SECONDS,
            }
        )
