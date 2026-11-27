"""End-to-end: real config entry, panel WebSocket commands, real recorder."""
import secrets
import time
from datetime import timedelta

import pytest
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.frontend import DATA_PANELS, EVENT_PANELS_UPDATED
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.inkview.const import (
    CONF_ALL_SENSORS,
    CONF_ALLOWED_ENTITIES,
    CONF_INSTANCE_ID,
    CONF_LINK_EXPIRES_AT,
    CONF_SECRET,
    DOMAIN,
    LINK_LIFETIME_SECONDS,
    PANEL_URL_PATH,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    # recorder_mock must be requested before hass is created.
    yield


def _entry(**data) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="InkView",
        data={
            CONF_INSTANCE_ID: "inst-setup",
            CONF_SECRET: secrets.token_hex(32),
            CONF_ALL_SENSORS: True,
            CONF_ALLOWED_ENTITIES: [],
            **data,
        },
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_pre_expiry_entry_gets_a_full_year(
    hass: HomeAssistant, hass_ws_client
) -> None:
    entry = _entry()  # created before link expiry existed
    await _setup(hass, entry)

    expires_at = entry.data[CONF_LINK_EXPIRES_AT]
    assert abs(expires_at - (time.time() + LINK_LIFETIME_SECONDS)) < 60

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "inkview/credentials"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["sessions"][0]["link_expires_at"] == expires_at


async def test_extend_link_service(hass: HomeAssistant) -> None:
    entry = _entry(**{CONF_LINK_EXPIRES_AT: time.time() + 3600})
    await _setup(hass, entry)

    await hass.services.async_call(DOMAIN, "extend_link", {}, blocking=True)
    await hass.async_block_till_done()

    assert entry.data[CONF_LINK_EXPIRES_AT] > time.time() + LINK_LIFETIME_SECONDS - 60


async def test_unloading_clears_link_issues(hass: HomeAssistant) -> None:
    entry = _entry(**{CONF_LINK_EXPIRES_AT: time.time() - 1})
    await _setup(hass, entry)
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, f"link_expired_{entry.entry_id}")

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not issues.async_get_issue(DOMAIN, f"link_expired_{entry.entry_id}")


async def test_panel_survives_reload_but_not_disable(hass: HomeAssistant) -> None:
    entry = _entry()
    await _setup(hass, entry)
    assert PANEL_URL_PATH in hass.data[DATA_PANELS]

    panel_events = async_capture_events(hass, EVENT_PANELS_UPDATED)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert panel_events == []

    await hass.config_entries.async_set_disabled_by(
        entry.entry_id, ConfigEntryDisabler.USER
    )
    assert PANEL_URL_PATH not in hass.data[DATA_PANELS]


async def test_rotate_secret_starts_a_new_link(hass: HomeAssistant) -> None:
    entry = _entry(**{CONF_LINK_EXPIRES_AT: time.time() + 3600})
    await _setup(hass, entry)
    old_secret = entry.data[CONF_SECRET]

    await hass.services.async_call(DOMAIN, "rotate_secret", {}, blocking=True)
    await hass.async_block_till_done()

    assert entry.data[CONF_SECRET] != old_secret
    assert entry.data[CONF_LINK_EXPIRES_AT] > time.time() + LINK_LIFETIME_SECONDS - 60
    session = hass.data[DOMAIN]["sessions"]["inst-setup"]
    assert session["secret"].hex() == entry.data[CONF_SECRET]


async def test_revoke_all_tokens_bumps_key_version(hass: HomeAssistant) -> None:
    entry = _entry(**{CONF_LINK_EXPIRES_AT: time.time() + 3600})
    await _setup(hass, entry)

    await hass.services.async_call(DOMAIN, "revoke_all_tokens", {}, blocking=True)
    await hass.async_block_till_done()

    assert entry.data["key_version"] == 2
    assert hass.data[DOMAIN]["sessions"]["inst-setup"]["key_version"] == 2


async def test_energy_summary_reads_real_statistics(
    hass: HomeAssistant, hass_ws_client
) -> None:
    await async_setup_component(hass, "sensor", {})
    entry = _entry(**{CONF_LINK_EXPIRES_AT: time.time() + 3600})
    await _setup(hass, entry)

    # Lifetime meter at 4,350 kWh; 18.5 kWh produced today.
    start = dt_util.start_of_local_day() - timedelta(hours=1)
    async_import_statistics(
        hass,
        {
            "source": "recorder",
            "statistic_id": "sensor.solar",
            "name": "Solar",
            "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
            "has_mean": False,
            "has_sum": True,
        },
        [
            {"start": start, "state": 4350.0, "sum": 1000.0},
            {"start": start + timedelta(hours=1), "state": 4360.0, "sum": 1010.0},
            {"start": start + timedelta(hours=2), "state": 4368.5, "sum": 1018.5},
        ],
    )
    await async_wait_recording_done(hass)
    hass.states.async_set(
        "sensor.solar",
        "4368.5",
        {
            "unit_of_measurement": "kWh",
            "state_class": "total_increasing",
            "friendly_name": "Solar",
        },
    )

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "inkview/energy_summary", "period": "today"})
    msg = await client.receive_json()
    assert msg["success"], msg
    result = msg["result"]
    assert result["source"] == "sensors"
    assert result["meters"] == [{"id": "sensor.solar", "name": "Solar", "kwh": 18.5}]


async def test_energy_summary_rejects_unknown_period(
    hass: HomeAssistant, hass_ws_client
) -> None:
    await _setup(hass, _entry(**{CONF_LINK_EXPIRES_AT: time.time() + 3600}))
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "inkview/energy_summary", "period": "decade"})
    msg = await client.receive_json()
    assert not msg["success"]
