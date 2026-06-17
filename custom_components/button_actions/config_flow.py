"""Config and options flow for Button Actions.

The whole mapping is entered/edited as a single YAML object — the same shape as
the YAML examples — so a configuration can be pasted, copied, or tweaked
(timeouts, actions) in one place.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_NAME,
    CONF_TRIGGER_ENTITY,
    DEFAULT_CLICK_WINDOW,
    DEFAULT_LONG_PRESS_TIME,
    DEFAULT_MODE,
    DOMAIN,
)
from .schema import MAPPING_SCHEMA

# The single form field holding the whole mapping as a YAML object.
CONF_CONFIG = "config"

# Prefilled in the add form so the expected shape is obvious.
TEMPLATE_MAPPING: dict[str, Any] = {
    CONF_NAME: "Room name",
    CONF_TRIGGER_ENTITY: "switch.shelly_input",
    "mode": DEFAULT_MODE,
    "click_window": DEFAULT_CLICK_WINDOW,
    "long_press_time": DEFAULT_LONG_PRESS_TIME,
    "fire_events": False,
    "single_click_action": [
        {"service": "light.toggle", "target": {"entity_id": ["light.strip_1"]}}
    ],
}


def _config_schema(default_value: Any) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CONFIG, default=default_value): selector.ObjectSelector(),
        }
    )


def _validate(raw: Any) -> dict[str, Any]:
    """Validate a pasted mapping; returns the normalized dict or raises."""
    if not isinstance(raw, dict):
        raise vol.Invalid("Expected a single mapping (a YAML object)")
    return MAPPING_SCHEMA(raw)


class ButtonActionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        raw: Any = TEMPLATE_MAPPING

        if user_input is not None:
            raw = user_input.get(CONF_CONFIG)
            try:
                mapping = _validate(raw)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                await self.async_set_unique_id(mapping[CONF_TRIGGER_ENTITY])
                self._abort_if_unique_id_configured()
                title = mapping.get(CONF_NAME) or mapping[CONF_TRIGGER_ENTITY]
                return self.async_create_entry(title=title, data=mapping)

        return self.async_show_form(
            step_id="user", data_schema=_config_schema(raw), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return ButtonActionsOptionsFlow(entry)


class ButtonActionsOptionsFlow(OptionsFlow):
    """Edit the whole mapping as YAML (prefilled with the current config)."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        raw: Any = dict(self._entry.data)

        if user_input is not None:
            raw = user_input.get(CONF_CONFIG)
            try:
                mapping = _validate(raw)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                new_trigger = mapping[CONF_TRIGGER_ENTITY]
                updates: dict[str, Any] = {
                    "data": mapping,
                    "title": mapping.get(CONF_NAME) or new_trigger,
                }
                if new_trigger != self._entry.unique_id:
                    if self._trigger_in_use(new_trigger):
                        errors["base"] = "already_configured"
                    else:
                        updates["unique_id"] = new_trigger

                if not errors:
                    self.hass.config_entries.async_update_entry(
                        self._entry, **updates
                    )
                    return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init", data_schema=_config_schema(raw), errors=errors
        )

    def _trigger_in_use(self, trigger_entity: str) -> bool:
        return any(
            entry.unique_id == trigger_entity and entry.entry_id != self._entry.entry_id
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )
