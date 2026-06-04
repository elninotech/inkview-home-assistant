"""Config + options + reauth flows for InkView."""
from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
)

from .const import (
    CONF_ALL_SENSORS,
    CONF_ALLOWED_ENTITIES,
    CONF_INSTANCE_ID,
    CONF_SECRET,
    CONF_SHOW_SIDEBAR_PANEL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _parse_secret(raw: str | None) -> bytes:
    raw = (raw or "").strip().lower()
    if len(raw) != 64:
        raise ValueError("secret must be 64 hex chars (32 bytes)")
    try:
        return bytes.fromhex(raw)
    except ValueError as e:
        raise ValueError("secret must be hex") from e


def _resolve_allowed(user_input: dict[str, Any]) -> list[str]:
    """Map the 'Expose all sensors' toggle + the picker into the stored
    allowlist. Toggle ON (the 'all') -> empty list == every renderable
    sensor. Toggle OFF -> exactly the picked sensors (possibly none)."""
    if user_input.get(CONF_ALL_SENSORS, True):
        return []
    return list(user_input.get(CONF_ALLOWED_ENTITIES) or [])


class InkViewConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manual-setup + reauth flows (phase-1; cloud pairing in phase-2)."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return InkViewOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        suggested_secret = secrets.token_hex(32)

        if user_input is not None:
            secret_bytes: bytes | None = None
            try:
                secret_bytes = _parse_secret(user_input.get(CONF_SECRET))
            except ValueError as e:
                _LOGGER.debug("bad_secret: %s", e)
                errors[CONF_SECRET] = "bad_secret"

            entities = _resolve_allowed(user_input)

            if not errors and secret_bytes is not None:
                instance_id = uuid.uuid4().hex
                await self.async_set_unique_id(instance_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, "InkView"),
                    data={
                        CONF_NAME: user_input.get(CONF_NAME, "InkView"),
                        CONF_INSTANCE_ID: instance_id,
                        CONF_SECRET: secret_bytes.hex(),
                        CONF_ALL_SENSORS: bool(
                            user_input.get(CONF_ALL_SENSORS, True)
                        ),
                        CONF_ALLOWED_ENTITIES: entities,
                        CONF_SHOW_SIDEBAR_PANEL: bool(
                            user_input.get(CONF_SHOW_SIDEBAR_PANEL, True)
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="InkView"): str,
                vol.Required(CONF_SECRET, default=suggested_secret): str,
                vol.Required(CONF_ALL_SENSORS, default=True): bool,
                vol.Optional(
                    CONF_ALLOWED_ENTITIES, default=[]
                ): EntitySelector(
                    EntitySelectorConfig(domain="sensor", multiple=True)
                ),
                vol.Optional(CONF_SHOW_SIDEBAR_PANEL, default=True): bool,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Triggered by the integration when the stored secret is no longer
        accepted (e.g. user rotated it externally). Surfaces the red banner
        in HA UI without losing the entry / its entity ids."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._reauth_entry is not None
        errors: dict[str, str] = {}
        suggested_secret = secrets.token_hex(32)

        if user_input is not None:
            try:
                secret_bytes = _parse_secret(user_input.get(CONF_SECRET))
            except ValueError as e:
                _LOGGER.debug("reauth bad_secret: %s", e)
                errors[CONF_SECRET] = "bad_secret"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_SECRET: secret_bytes.hex(),
                    },
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {vol.Required(CONF_SECRET, default=suggested_secret): str}
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )


class InkViewOptionsFlow(OptionsFlow):
    """Edit allowed_entities (and future per-entry settings) without losing
    the entry. Stored under entry.options so HA's "are there pending changes?"
    indicator works correctly."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_ALL_SENSORS: bool(
                        user_input.get(CONF_ALL_SENSORS, True)
                    ),
                    CONF_ALLOWED_ENTITIES: _resolve_allowed(user_input),
                    CONF_SHOW_SIDEBAR_PANEL: bool(
                        user_input.get(CONF_SHOW_SIDEBAR_PANEL, True)
                    ),
                },
            )

        # Options take precedence over the original data so users see what
        # was actually applied last.
        current_entities = list(
            self._entry.options.get(
                CONF_ALLOWED_ENTITIES,
                self._entry.data.get(CONF_ALLOWED_ENTITIES, []),
            )
        )
        # An empty allowlist means "all sensors". Default the toggle to match
        # whatever's currently stored so re-opening options is non-destructive.
        current_all = bool(
            self._entry.options.get(
                CONF_ALL_SENSORS,
                self._entry.data.get(CONF_ALL_SENSORS, not current_entities),
            )
        )
        current_panel = bool(
            self._entry.options.get(
                CONF_SHOW_SIDEBAR_PANEL,
                self._entry.data.get(CONF_SHOW_SIDEBAR_PANEL, True),
            )
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_ALL_SENSORS, default=current_all): bool,
                vol.Optional(
                    CONF_ALLOWED_ENTITIES, default=current_entities
                ): EntitySelector(
                    EntitySelectorConfig(domain="sensor", multiple=True)
                ),
                vol.Optional(
                    CONF_SHOW_SIDEBAR_PANEL, default=current_panel
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
