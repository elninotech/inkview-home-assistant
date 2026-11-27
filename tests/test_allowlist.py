"""Sensor grant and effective_allowlist: None = all sensors, empty set = deny all."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.inkview.const import (
    CONF_ALL_SENSORS,
    CONF_ALLOWED_ENTITIES,
    DOMAIN,
)
from custom_components.inkview.grant import entry_grant, grant_set
from custom_components.inkview.http_views._common import effective_allowlist

ALL = {"all_sensors": True, "allowed_entities": []}


def _only(*ids: str) -> dict:
    return {"all_sensors": False, "allowed_entities": list(ids)}


def test_entry_all_sensors_is_none():
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ALL_SENSORS: True, CONF_ALLOWED_ENTITIES: []},
    )
    assert entry_grant(entry) is None


def test_entry_restricted_with_nothing_picked_is_empty_not_all():
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ALL_SENSORS: False, CONF_ALLOWED_ENTITIES: []},
    )
    assert entry_grant(entry) == []


def test_entry_restricted_list():
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ALL_SENSORS: False, CONF_ALLOWED_ENTITIES: ["sensor.a"]},
    )
    assert entry_grant(entry) == ["sensor.a"]


def test_entry_options_override_data():
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ALL_SENSORS: True, CONF_ALLOWED_ENTITIES: []},
        options={CONF_ALL_SENSORS: False, CONF_ALLOWED_ENTITIES: []},
    )
    assert entry_grant(entry) == []


def test_entry_without_toggle_keeps_legacy_meaning():
    legacy_all = MockConfigEntry(domain=DOMAIN, data={CONF_ALLOWED_ENTITIES: []})
    legacy_list = MockConfigEntry(
        domain=DOMAIN, data={CONF_ALLOWED_ENTITIES: ["sensor.a"]}
    )
    assert entry_grant(legacy_all) is None
    assert entry_grant(legacy_list) == ["sensor.a"]


def test_grant_set_normalisation():
    assert grant_set(ALL) is None
    assert grant_set(_only()) == set()
    assert grant_set(_only("sensor.a")) == {"sensor.a"}


def test_grant_set_fails_closed_without_explicit_flag():
    # Legacy bearers have no all_sensors flag.
    assert grant_set({"allowed_entities": []}) == set()
    assert grant_set({}) == set()
    assert grant_set({"all_sensors": "true"}) == set()  # only literal True


def test_both_all_returns_none():
    assert effective_allowlist(ALL, ALL) is None


def test_restricted_empty_session_denies_an_all_token():
    out = effective_allowlist(ALL, _only())
    assert out == set()
    assert out is not None


def test_restricted_empty_token_denies_an_all_session():
    assert effective_allowlist(_only(), ALL) == set()


def test_legacy_empty_token_denies_even_when_session_is_all():
    assert effective_allowlist({"allowed_entities": []}, ALL) == set()


def test_session_narrows_an_all_token():
    out = effective_allowlist(ALL, _only("sensor.a", "sensor.b"))
    assert out == {"sensor.a", "sensor.b"}


def test_token_constrains_when_session_is_all():
    assert effective_allowlist(_only("sensor.a"), ALL) == {"sensor.a"}


def test_intersection_is_more_restrictive():
    out = effective_allowlist(
        _only("sensor.a", "sensor.b"), _only("sensor.b", "sensor.c")
    )
    assert out == {"sensor.b"}


def test_disjoint_grants_deny_all_not_all():
    out = effective_allowlist(_only("sensor.a"), _only("sensor.b"))
    assert out == set()
    assert out is not None
