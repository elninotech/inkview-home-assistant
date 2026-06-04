"""Helpers shared by InkView HTTP views."""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from ..auth.bearer import InvalidToken, parse_unverified_subject, verify
from ..const import DATA_SESSIONS, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _reject(session: dict[str, Any] | None, reason: str) -> web.Response:
    """401 with stats side-effect. Stable error body across all reject paths
    so an attacker can't tell *which* check failed."""
    if session is not None and "stats" in session:
        session["stats"].record_failed_auth()
    _LOGGER.debug("bearer rejected: %s", reason)
    return web.json_response({"error": "invalid_token"}, status=401)


def authenticate_bearer(
    request: web.Request,
) -> tuple[dict[str, Any], dict[str, Any]] | web.Response:
    """Validate Authorization: Bearer <jwt>.

    Returns (claims, session) on success or an HTTP 401 response on any
    failure. Every failure mode returns the same body so an attacker
    can't enumerate which instance_ids exist."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        # Same body as every other auth failure so callers can't distinguish
        # "no header" from "bad token" — and can't enumerate instances.
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

    # key_version gate: bumped by `inkview.revoke_all_tokens` to invalidate
    # outstanding bearers without changing the underlying HMAC secret.
    expected_kv = int(session.get("key_version", 1))
    presented_kv = claims.get("kv")
    if not isinstance(presented_kv, int) or presented_kv < expected_kv:
        return _reject(session, "stale key_version")

    # Read-only gate: every InkView endpoint is read-only, so a token must
    # carry the read scope (or, for backward-compat, omit it entirely). A
    # token explicitly scoped to anything else is refused outright.
    if claims.get("scope", "read") != "read":
        return _reject(session, "non-read scope")

    return claims, session


def _as_allowset(value: Any) -> set[str] | None:
    """Normalise an allowlist: a non-empty collection becomes a set; an empty
    or missing one becomes None, the sentinel for 'all renderable sensors'."""
    s = {str(v) for v in (value or [])}
    return s or None


def effective_allowlist(
    claims: dict[str, Any], session: dict[str, Any]
) -> set[str] | None:
    """Entity ids a request may read — or None for 'all renderable sensors'.

    A token freezes the allowlist captured when it was minted, but bearers
    live up to a year. To honour scope changes immediately we combine the
    token's grant with the session's *current* allowlist and return the more
    restrictive of the two: tightening the allowlist in options takes effect
    at once, and a token is never broadened beyond what it was issued for.

    An empty set is returned (not None) when the two grants don't overlap —
    that means 'read nothing', which callers must treat as deny-all, distinct
    from the None 'read everything' sentinel."""
    token_allowed = _as_allowset(claims.get("allowed_entities"))
    session_allowed = _as_allowset(session.get("allowed_entities"))
    if token_allowed is None:
        return session_allowed
    if session_allowed is None:
        return token_allowed
    return token_allowed & session_allowed
