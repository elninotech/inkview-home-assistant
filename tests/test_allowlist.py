"""Tests for effective_allowlist — the per-request authorization boundary.

None means "all renderable sensors"; a set (possibly empty) is a strict
allowlist, where the empty set means "deny everything". The function returns
the more restrictive of the token's frozen grant and the session's current
allowlist, so tightening scope in options applies to already-issued tokens.
"""
from custom_components.inkview.http_views._common import (
    _as_allowset,
    effective_allowlist,
)


def test_as_allowset_normalisation():
    assert _as_allowset(None) is None
    assert _as_allowset([]) is None              # empty == "all"
    assert _as_allowset(["sensor.a"]) == {"sensor.a"}


def test_both_all_returns_none():
    assert effective_allowlist({}, {}) is None
    assert effective_allowlist(
        {"allowed_entities": []}, {"allowed_entities": []}
    ) is None


def test_session_narrows_an_all_token():
    out = effective_allowlist({}, {"allowed_entities": ["sensor.a", "sensor.b"]})
    assert out == {"sensor.a", "sensor.b"}


def test_token_constrains_when_session_is_all():
    out = effective_allowlist({"allowed_entities": ["sensor.a"]}, {})
    assert out == {"sensor.a"}


def test_intersection_is_more_restrictive():
    out = effective_allowlist(
        {"allowed_entities": ["sensor.a", "sensor.b"]},
        {"allowed_entities": ["sensor.b", "sensor.c"]},
    )
    assert out == {"sensor.b"}


def test_disjoint_grants_deny_all_not_all():
    out = effective_allowlist(
        {"allowed_entities": ["sensor.a"]},
        {"allowed_entities": ["sensor.b"]},
    )
    assert out == set()
    assert out is not None  # empty set = deny everything, NOT "all sensors"
