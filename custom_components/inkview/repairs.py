"""Repair issues surfaced in Settings → Repairs.

We use informational `async_create_issue` rather than a fixable RepairsFlow:
the user fixes this by picking sensors in the integration's options, not in
a popup. The `learn_more_url` deep-links to the integration page."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, ISSUE_NO_ENERGY_SENSORS

_LOGGER = logging.getLogger(__name__)


def report_energy_state(hass: HomeAssistant, has_energy_sensors: bool) -> None:
    """Create or clear the 'no energy sensors' issue.

    Called from the energy coordinator on every successful refresh. Idempotent;
    HA's issue registry handles the dedupe on create."""
    if has_energy_sensors:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_NO_ENERGY_SENSORS)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_NO_ENERGY_SENSORS,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_NO_ENERGY_SENSORS,
        learn_more_url="/config/integrations/integration/inkview",
    )
