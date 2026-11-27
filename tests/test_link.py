"""Tests for link expiry and its Repairs issues."""
import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.inkview.const import (
    CONF_LINK_EXPIRES_AT,
    DOMAIN,
    LINK_LIFETIME_SECONDS,
)
from custom_components.inkview.link import (
    async_update_link_issues,
    link_expired,
    new_link_expiry,
)

DAY = 86400


def _entry(expires_at: float) -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data={CONF_LINK_EXPIRES_AT: expires_at})


def _issues(hass: HomeAssistant, entry: MockConfigEntry) -> set[str]:
    reg = ir.async_get(hass)
    return {
        kind
        for kind in ("link_expiring", "link_expired")
        if reg.async_get_issue(DOMAIN, f"{kind}_{entry.entry_id}") is not None
    }


def test_new_link_lasts_a_year():
    assert new_link_expiry(1000) == 1000 + LINK_LIFETIME_SECONDS


def test_link_expired_fails_closed():
    now = time.time()
    assert not link_expired({CONF_LINK_EXPIRES_AT: now + 60}, now)
    assert link_expired({CONF_LINK_EXPIRES_AT: now}, now)
    assert link_expired({}, now)


async def test_no_issue_while_plenty_of_time_remains(hass: HomeAssistant) -> None:
    entry = _entry(time.time() + 60 * DAY)
    async_update_link_issues(hass, entry)
    assert _issues(hass, entry) == set()


async def test_warns_inside_two_weeks(hass: HomeAssistant) -> None:
    entry = _entry(time.time() + 5 * DAY)
    async_update_link_issues(hass, entry)
    assert _issues(hass, entry) == {"link_expiring"}
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"link_expiring_{entry.entry_id}")
    assert issue.translation_placeholders["days"] == "4"


async def test_expired_replaces_the_warning(hass: HomeAssistant) -> None:
    entry = _entry(time.time() + 5 * DAY)
    async_update_link_issues(hass, entry)
    async_update_link_issues(hass, entry, now=time.time() + 6 * DAY)
    assert _issues(hass, entry) == {"link_expired"}


async def test_extending_clears_the_issue(hass: HomeAssistant) -> None:
    entry = _entry(time.time() - 1)
    entry.add_to_hass(hass)
    async_update_link_issues(hass, entry)
    assert _issues(hass, entry) == {"link_expired"}

    hass.config_entries.async_update_entry(
        entry, data={CONF_LINK_EXPIRES_AT: new_link_expiry()}
    )
    async_update_link_issues(hass, entry)
    assert _issues(hass, entry) == set()
