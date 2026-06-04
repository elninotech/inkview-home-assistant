"""Security tests for the stdlib JWT/HMAC primitives in auth/bearer.py.

These cover the properties the auth layer relies on: signatures are verified,
the header `alg` cannot be used to bypass verification, reserved claims can't
be forged through extra_claims, and HMAC request signing binds ts + nonce.
"""
import base64
import hashlib
import hmac
import json
import time

import pytest

from custom_components.inkview.auth import bearer

SECRET = b"\x11" * 32
OTHER_SECRET = b"\x22" * 32


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _signed(claims: dict, secret: bytes = SECRET) -> str:
    """Hand-build a correctly HS256-signed token from arbitrary claims."""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, sort_keys=True).encode())
    payload = _b64(json.dumps(claims, sort_keys=True).encode())
    sig = _b64(hmac.new(secret, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def _valid_claims(**overrides) -> dict:
    now = int(time.time())
    claims = {
        "sub": "inst-1", "iss": "inkview-ha", "aud": "inkview-server",
        "exp": now + 60, "nbf": now, "kv": 1,
    }
    claims.update(overrides)
    return claims


def test_mint_verify_roundtrip():
    token, exp = bearer.mint(
        SECRET, sub="inst-1", key_version=1,
        extra_claims={"scope": "read", "allowed_entities": ["sensor.a"]},
    )
    claims = bearer.verify(SECRET, token)
    assert claims["sub"] == "inst-1"
    assert claims["scope"] == "read"
    assert claims["allowed_entities"] == ["sensor.a"]
    assert claims["kv"] == 1
    assert claims["exp"] == exp


def test_wrong_secret_rejected():
    token, _ = bearer.mint(SECRET, sub="inst-1", key_version=1)
    with pytest.raises(bearer.InvalidToken):
        bearer.verify(OTHER_SECRET, token)


def test_tampered_payload_rejected():
    token, _ = bearer.mint(SECRET, sub="inst-1", key_version=1)
    h, p, s = token.split(".")
    flipped = p[:-1] + ("A" if p[-1] != "A" else "B")
    with pytest.raises(bearer.InvalidToken):
        bearer.verify(SECRET, f"{h}.{flipped}.{s}")


def test_alg_none_confusion_rejected():
    # Attacker switches header to alg=none and drops the signature.
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps(_valid_claims()).encode())
    with pytest.raises(bearer.InvalidToken):
        bearer.verify(SECRET, f"{header}.{payload}.")


def test_malformed_token_rejected():
    with pytest.raises(bearer.InvalidToken):
        bearer.verify(SECRET, "not-a-jwt")


def test_expired_rejected():
    token, _ = bearer.mint(SECRET, sub="inst-1", key_version=1, ttl_seconds=-100)
    with pytest.raises(bearer.InvalidToken):
        bearer.verify(SECRET, token)


def test_not_yet_valid_rejected():
    token = _signed(_valid_claims(nbf=int(time.time()) + 3600))
    with pytest.raises(bearer.InvalidToken):
        bearer.verify(SECRET, token)


def test_bad_issuer_rejected():
    token = _signed(_valid_claims(iss="someone-else"))
    with pytest.raises(bearer.InvalidToken):
        bearer.verify(SECRET, token)


def test_bad_audience_rejected():
    token = _signed(_valid_claims(aud="someone-else"))
    with pytest.raises(bearer.InvalidToken):
        bearer.verify(SECRET, token)


def test_reserved_claims_cannot_be_forged():
    # extra_claims must not be able to override iss / aud / exp.
    token, exp = bearer.mint(
        SECRET, sub="inst-1", key_version=1,
        extra_claims={"iss": "evil", "aud": "evil", "exp": 1},
    )
    claims = bearer.verify(SECRET, token)
    assert claims["iss"] == "inkview-ha"
    assert claims["aud"] == "inkview-server"
    assert claims["exp"] == exp != 1


def test_parse_unverified_subject():
    token, _ = bearer.mint(SECRET, sub="abc", key_version=1)
    assert bearer.parse_unverified_subject(token) == "abc"
    assert bearer.parse_unverified_subject("garbage") is None
    assert bearer.parse_unverified_subject("only.one") is None


def test_hmac_roundtrip_and_binding():
    body = b"inst-1"
    sig = bearer.sign_hmac(SECRET, body, "1700000000", "nonce-abc")
    assert bearer.verify_hmac(SECRET, body, "1700000000", "nonce-abc", sig)
    # Any change to ts, nonce, body, or secret must break verification.
    assert not bearer.verify_hmac(SECRET, body, "1700000001", "nonce-abc", sig)
    assert not bearer.verify_hmac(SECRET, body, "1700000000", "nonce-xyz", sig)
    assert not bearer.verify_hmac(SECRET, b"inst-2", "1700000000", "nonce-abc", sig)
    assert not bearer.verify_hmac(OTHER_SECRET, body, "1700000000", "nonce-abc", sig)
