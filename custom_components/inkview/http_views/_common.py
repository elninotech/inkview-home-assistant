"""Helpers shared by InkView HTTP views."""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from ..auth.bearer import InvalidToken, parse_unverified_subject, verify
from ..const import DATA_SESSIONS, DOMAIN
from ..grant import grant_set
from ..link import link_expired

_LOGGER = logging.getLogger(__name__)


def _reject(session: dict[str, Any] | None, reason: str) -> web.Response:
    """Uniform 401 body so callers can't tell which check failed or enumerate instances."""
    if session is not None and "stats" in session:
        session["stats"].record_failed_auth()
    _LOGGER.debug("bearer rejected: %s", reason)
    return web.json_response({"error": "invalid_token"}, status=401)


def authenticate_bearer(
    request: web.Request,
) -> tuple[dict[str, Any], dict[str, Any]] | web.Response:
    """Return (claims, session) for a valid bearer, else a uniform 401 response."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return _reject(None, "missing bearer")
    token = auth[7:].strip()
    if not token:
        return _reject(None, "empty token")

    instance_id = parse_unverified_subject(token)
    if instance_id is None:
        return _reject(None, "no subject")

    hass = request.app["hass"]
    sessions = hass.data.get(DOMAIN, {}).get(DATA_SESSIONS, {})
    session = sessions.get(instance_id)
    if session is None:
        return _reject(None, "unknown instance")
    try:
        claims = verify(session["secret"], token)
    except InvalidToken as e:
        return _reject(session, str(e))

    # Revocation: revoke_all_tokens bumps key_version.
    expected_kv = int(session.get("key_version", 1))
    presented_kv = claims.get("kv")
    if not isinstance(presented_kv, int) or presented_kv < expected_kv:
        return _reject(session, "stale key_version")

    # Defence in depth; minted TTL is already capped at link expiry.
    if link_expired(session):
        return _reject(session, "link expired")

    # Read-only gate: a missing scope counts as "read"; any other scope is refused.
    if claims.get("scope", "read") != "read":
        return _reject(session, "non-read scope")

    return claims, session


def effective_allowlist(
    claims: dict[str, Any], session: dict[str, Any]
) -> set[str] | None:
    """Stricter of the token's and the session's current grant (bearers live up to a year).

    None = all renderable sensors; an empty set = deny all."""
    token_allowed = grant_set(claims)
    session_allowed = grant_set(session)
    if token_allowed is None:
        return session_allowed
    if session_allowed is None:
        return token_allowed
    return token_allowed & session_allowed
