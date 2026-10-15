"""End-to-end grant enforcement through the real HTTP views.

Mints a bearer via the client-credentials view, then reads through every
bearer endpoint, so the grant is exercised from config entry -> session ->
token claims -> per-request allowlist. Views are called directly with a
minimal request stand-in (they only touch .app, .headers and .content).
"""
import json
import secrets
import time

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.inkview.auth import bearer
from custom_components.inkview.auth.stats import SessionStats
from custom_components.inkview.const import (
    CONF_ALL_SENSORS,
    CONF_ALLOWED_ENTITIES,
    DATA_SESSIONS,
    DOMAIN,
)
from custom_components.inkview.grant import entry_grant
from custom_components.inkview.http_views.auth import InkViewAuthTokenView
from custom_components.inkview.http_views.energy import InkViewEnergyTotalsView
from custom_components.inkview.http_views.states import InkViewStateView
from custom_components.inkview.http_views.states_batch import InkViewBatchStateView
from custom_components.inkview.http_views.states_list import InkViewStatesListView

INSTANCE_ID = "inst-eln-380"
SECRET = b"\x33" * 32


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, _n: int = -1) -> bytes:
        return self._data


class _Request:
    def __init__(self, hass, *, token=None, body=b"") -> None:
        self.app = {"hass": hass}
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.content = _Body(body)


def _json(resp) -> dict:
    return json.loads(resp.body)


def _seed_states(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.a", "10", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.b", "20", {"unit_of_measurement": "kWh"})


def _install_session(hass: HomeAssistant, *, all_sensors, allowed) -> None:
    """Build the session exactly as async_setup_entry does."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ALL_SENSORS: all_sensors, CONF_ALLOWED_ENTITIES: allowed},
    )
    grant = entry_grant(entry)
    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_SESSIONS, {})[INSTANCE_ID] = {
        "entry_id": entry.entry_id,
        "secret": SECRET,
        "all_sensors": grant is None,
        "allowed_entities": grant or [],
        "key_version": 1,
        "stats": SessionStats(),
    }


async def _mint(hass: HomeAssistant) -> str:
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(12)
    sig = bearer.sign_hmac(SECRET, INSTANCE_ID.encode("ascii"), ts, nonce)
    body = json.dumps(
        {"instance_id": INSTANCE_ID, "ts": ts, "nonce": nonce, "sig": sig}
    ).encode()
    resp = await InkViewAuthTokenView().post(_Request(hass, body=body))
    assert resp.status == 200, resp.body
    return _json(resp)["access_token"]


async def _list(hass, token) -> list[str]:
    resp = await InkViewStatesListView().get(_Request(hass, token=token))
    assert resp.status == 200
    return [s["entity_id"] for s in _json(resp)["sensors"]]


async def _batch(hass, token) -> dict:
    body = json.dumps({"entity_ids": ["sensor.a", "sensor.b"]}).encode()
    resp = await InkViewBatchStateView().post(_Request(hass, token=token, body=body))
    assert resp.status == 200
    return _json(resp)["states"]


async def _energy(hass, token) -> dict:
    resp = await InkViewEnergyTotalsView().get(_Request(hass, token=token))
    assert resp.status == 200
    return _json(resp)


async def test_restricted_grant_with_no_sensors_exposes_nothing(
    hass: HomeAssistant,
) -> None:
    """ELN-380: 'Expose all sensors' off + nothing picked must read nothing."""
    _seed_states(hass)
    _install_session(hass, all_sensors=False, allowed=[])
    token = await _mint(hass)

    claims = bearer.verify(SECRET, token)
    assert claims["all_sensors"] is False
    assert claims["allowed_entities"] == []

    assert await _list(hass, token) == []

    resp = await InkViewStateView().get(_Request(hass, token=token), "sensor.a")
    assert resp.status == 403

    states = await _batch(hass, token)
    assert states == {
        "sensor.a": {"error": "entity_not_allowed"},
        "sensor.b": {"error": "entity_not_allowed"},
    }

    energy = await _energy(hass, token)
    assert energy["sensor_count"] == 0
    assert energy["total_energy_kwh"] == pytest.approx(0.0)


async def test_all_sensors_grant_exposes_every_renderable_sensor(
    hass: HomeAssistant,
) -> None:
    _seed_states(hass)
    _install_session(hass, all_sensors=True, allowed=[])
    token = await _mint(hass)

    assert bearer.verify(SECRET, token)["all_sensors"] is True
    assert sorted(await _list(hass, token)) == ["sensor.a", "sensor.b"]

    resp = await InkViewStateView().get(_Request(hass, token=token), "sensor.a")
    assert resp.status == 200

    energy = await _energy(hass, token)
    assert energy["sensor_count"] == 2
    assert energy["total_energy_kwh"] == pytest.approx(30.0)


async def test_restricted_grant_exposes_only_picked_sensors(
    hass: HomeAssistant,
) -> None:
    _seed_states(hass)
    _install_session(hass, all_sensors=False, allowed=["sensor.a"])
    token = await _mint(hass)

    assert await _list(hass, token) == ["sensor.a"]
    states = await _batch(hass, token)
    assert states["sensor.b"] == {"error": "entity_not_allowed"}
    assert (await _energy(hass, token))["total_energy_kwh"] == pytest.approx(10.0)


async def test_narrowing_to_nothing_revokes_an_all_token(
    hass: HomeAssistant,
) -> None:
    """A token minted under 'all' stops reading the moment the grant is
    narrowed to nothing — the session's current grant always applies."""
    _seed_states(hass)
    _install_session(hass, all_sensors=True, allowed=[])
    token = await _mint(hass)

    _install_session(hass, all_sensors=False, allowed=[])
    assert await _list(hass, token) == []


async def test_pre_fix_token_with_empty_list_fails_closed(
    hass: HomeAssistant,
) -> None:
    """Bearers minted before the explicit flag carry a bare `[]`; that must
    not be read as 'all', even if the session currently grants everything."""
    _seed_states(hass)
    _install_session(hass, all_sensors=True, allowed=[])
    legacy, _ = bearer.mint(
        SECRET,
        sub=INSTANCE_ID,
        key_version=1,
        extra_claims={"allowed_entities": [], "scope": "read"},
    )
    assert await _list(hass, legacy) == []
