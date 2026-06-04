"""HS256 JWT mint/verify and HMAC request signing.

Implemented in stdlib only so the integration carries zero third-party
runtime dependencies. HA already ships `cryptography`, but for HMAC-SHA256
the `hmac` + `hashlib` stdlib modules are sufficient and lighter."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


class InvalidToken(Exception):
    """Raised when a presented token is malformed, tampered, or expired."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def mint(
    secret: bytes,
    *,
    sub: str,
    key_version: int,
    aud: str = "inkview-server",
    iss: str = "inkview-ha",
    ttl_seconds: int = 900,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """Sign a JWT and return (token, exp_unix). Reserved claims always win
    over `extra_claims` so callers can't forge issuer/audience/expiry.

    `key_version` is embedded as `kv`. Bumping the session's key_version
    invalidates every previously-issued token without rotating the
    underlying HMAC secret — that's how `inkview.revoke_all_tokens` works."""
    now = int(time.time())
    exp = now + ttl_seconds
    claims: dict[str, Any] = {}
    if extra_claims:
        claims.update(extra_claims)
    claims.update(
        {
            "iss": iss,
            "sub": sub,
            "aud": aud,
            "iat": now,
            "nbf": now,
            "exp": exp,
            "jti": secrets.token_urlsafe(12),
            "kv": int(key_version),
        }
    )

    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    p = _b64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{h}.{p}".encode("ascii")
    sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}", exp


def verify(
    secret: bytes,
    token: str,
    *,
    aud: str = "inkview-server",
    iss: str = "inkview-ha",
    leeway_seconds: int = 5,
) -> dict[str, Any]:
    """Constant-time signature check + claim validation."""
    if not isinstance(token, str) or token.count(".") != 2:
        raise InvalidToken("malformed")
    h, p, s = token.split(".")
    signing_input = f"{h}.{p}".encode("ascii")
    expected = hmac.new(secret, signing_input, hashlib.sha256).digest()
    try:
        received = _b64url_decode(s)
    except Exception as e:
        raise InvalidToken("malformed signature") from e
    if not hmac.compare_digest(expected, received):
        raise InvalidToken("bad signature")
    try:
        claims = json.loads(_b64url_decode(p))
    except Exception as e:
        raise InvalidToken("malformed payload") from e
    if not isinstance(claims, dict):
        raise InvalidToken("malformed payload")

    now = int(time.time())
    exp = claims.get("exp")
    nbf = claims.get("nbf", 0)
    if not isinstance(exp, int) or now > exp + leeway_seconds:
        raise InvalidToken("expired")
    if not isinstance(nbf, int) or now + leeway_seconds < nbf:
        raise InvalidToken("not yet valid")
    if claims.get("iss") != iss:
        raise InvalidToken("bad issuer")
    if claims.get("aud") != aud:
        raise InvalidToken("bad audience")
    return claims


def parse_unverified_subject(token: str) -> str | None:
    """Peek at the `sub` claim without verifying the signature.
    Used only to look up which session's secret to verify with."""
    if not isinstance(token, str) or token.count(".") != 2:
        return None
    _, p, _ = token.split(".")
    try:
        payload = json.loads(_b64url_decode(p))
    except Exception:
        return None
    sub = payload.get("sub") if isinstance(payload, dict) else None
    return sub if isinstance(sub, str) else None


def sign_hmac(secret: bytes, body: bytes, ts: str, nonce: str) -> str:
    msg = body + b"|" + ts.encode("ascii") + b"|" + nonce.encode("ascii")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify_hmac(secret: bytes, body: bytes, ts: str, nonce: str, sig: str) -> bool:
    expected = sign_hmac(secret, body, ts, nonce)
    return hmac.compare_digest(expected, sig)
