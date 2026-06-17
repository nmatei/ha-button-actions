"""Config and options flow for Button Actions.

Both adding and editing offer two ways to configure a mapping:

* **Guided** — friendly fields (trigger entity, mode, timeouts) plus a target
  picker per gesture, with an optional advanced YAML action that overrides it.
* **YAML** — the whole mapping as one YAML object, same shape as the examples,
  so it can be pasted/copied/tweaked in one place.

Both paths produce the same normalized mapping (validated by MAPPING_SCHEMA).
"""

from __future__ import annotations

from typing import Any, Optional

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
    CONF_CLICK_WINDOW,
    CONF_DOUBLE_CLICK_ACTION,
    CONF_FIRE_EVENTS,
    CONF_LONG_PRESS_ACTION,
    CONF_LONG_PRESS_TIME,
    CONF_MODE,
    CONF_NAME,
    CONF_SINGLE_CLICK_ACTION,
    CONF_TRIGGER_ENTITY,
    DEFAULT_CLICK_WINDOW,
    DEFAULT_FIRE_EVENTS,
    DEFAULT_LONG_PRESS_TIME,
    DEFAULT_MODE,
    DOMAIN,
    MODES,
)
from .schema import MAPPING_SCHEMA

# The single field that holds the whole mapping in the YAML step.
CONF_CONFIG = "config"

# (action key, UI-only target-picker key) per gesture.
_GESTURES = (
    (CONF_SINGLE_CLICK_ACTION, "single_click_targets"),
    (CONF_DOUBLE_CLICK_ACTION, "double_click_targets"),
    (CONF_LONG_PRESS_ACTION, "long_press_targets"),
)

# Prefilled in the YAML add step so the expected shape is obvious.
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


def _has_targets(target: Any) -> bool:
    if not isinstance(target, dict):
        return False
    return any(target.get(key) for key in ("entity_id", "device_id", "area_id"))


def _form_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Guided multi-field schema, prefilled from ``defaults``."""

    def d(key: str, fallback: Any) -> Any:
        value = defaults.get(key, fallback)
        return value if value is not None else fallback

    schema: dict[Any, Any] = {
        vol.Optional(CONF_NAME, default=d(CONF_NAME, "")): selector.TextSelector(),
        vol.Required(
            CONF_TRIGGER_ENTITY, default=d(CONF_TRIGGER_ENTITY, vol.UNDEFINED)
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["switch", "binary_sensor", "input_boolean"]
            )
        ),
        vol.Optional(CONF_MODE, default=d(CONF_MODE, DEFAULT_MODE)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(MODES),
                translation_key="mode",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(
            CONF_CLICK_WINDOW, default=d(CONF_CLICK_WINDOW, DEFAULT_CLICK_WINDOW)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=100, max=3000, step=50, unit_of_measurement="ms"
            )
        ),
        vol.Optional(
            CONF_LONG_PRESS_TIME, default=d(CONF_LONG_PRESS_TIME, DEFAULT_LONG_PRESS_TIME)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=300, max=5000, step=50, unit_of_measurement="ms"
            )
        ),
        vol.Optional(
            CONF_FIRE_EVENTS, default=d(CONF_FIRE_EVENTS, DEFAULT_FIRE_EVENTS)
        ): selector.BooleanSelector(),
    }

    for action_key, target_key in _GESTURES:
        schema[
            vol.Optional(target_key, default=defaults.get(target_key, {}))
        ] = selector.TargetSelector()
        action_default = defaults.get(action_key)
        marker = (
            vol.Optional(action_key, default=action_default)
            if action_default
            else vol.Optional(action_key)
        )
        schema[marker] = selector.ObjectSelector()

    return vol.Schema(schema)


def _config_schema(default_value: Any) -> vol.Schema:
    """Single-field YAML schema."""
    return vol.Schema(
        {vol.Required(CONF_CONFIG, default=default_value): selector.ObjectSelector()}
    )


def _build_from_form(user_input: dict[str, Any]) -> dict[str, Any]:
    """Turn guided form input into a normalized, validated mapping."""
    mapping: dict[str, Any] = {
        CONF_TRIGGER_ENTITY: user_input.get(CONF_TRIGGER_ENTITY),
        CONF_MODE: user_input.get(CONF_MODE, DEFAULT_MODE),
        CONF_CLICK_WINDOW: int(user_input.get(CONF_CLICK_WINDOW, DEFAULT_CLICK_WINDOW)),
        CONF_LONG_PRESS_TIME: int(
            user_input.get(CONF_LONG_PRESS_TIME, DEFAULT_LONG_PRESS_TIME)
        ),
        CONF_FIRE_EVENTS: user_input.get(CONF_FIRE_EVENTS, DEFAULT_FIRE_EVENTS),
    }
    name = (user_input.get(CONF_NAME) or "").strip()
    if name:
        mapping[CONF_NAME] = name

    for action_key, target_key in _GESTURES:
        action = user_input.get(action_key)
        target = user_input.get(target_key)
        if action:  # an explicit YAML action wins over the target picker
            mapping[action_key] = action
        elif _has_targets(target):
            mapping[action_key] = [
                {"service": "homeassistant.toggle", "target": target}
            ]

    return MAPPING_SCHEMA(mapping)


def _validate_yaml(raw: Any) -> dict[str, Any]:
    """Validate a pasted whole-mapping YAML object."""
    if not isinstance(raw, dict):
        raise vol.Invalid("Expected a single mapping (a YAML object)")
    return MAPPING_SCHEMA(raw)


class ButtonActionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(step_id="user", menu_options=["form", "yaml"])

    async def async_step_form(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                mapping = _build_from_form(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                return await self._create(mapping)
        return self.async_show_form(
            step_id="form", data_schema=_form_schema(user_input or {}), errors=errors
        )

    async def async_step_yaml(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        raw: Any = TEMPLATE_MAPPING
        if user_input is not None:
            raw = user_input.get(CONF_CONFIG)
            try:
                mapping = _validate_yaml(raw)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                return await self._create(mapping)
        return self.async_show_form(
            step_id="yaml", data_schema=_config_schema(raw), errors=errors
        )

    async def _create(self, mapping: dict[str, Any]) -> FlowResult:
        await self.async_set_unique_id(mapping[CONF_TRIGGER_ENTITY])
        self._abort_if_unique_id_configured()
        title = mapping.get(CONF_NAME) or mapping[CONF_TRIGGER_ENTITY]
        return self.async_create_entry(title=title, data=mapping)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return ButtonActionsOptionsFlow(entry)


class ButtonActionsOptionsFlow(OptionsFlow):
    """Edit a mapping via guided fields or whole-mapping YAML."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(step_id="init", menu_options=["form", "yaml"])

    async def async_step_form(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                mapping = _build_from_form(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                result = self._apply(mapping, errors)
                if result is not None:
                    return result
        defaults = user_input if user_input is not None else dict(self._entry.data)
        return self.async_show_form(
            step_id="form", data_schema=_form_schema(defaults), errors=errors
        )

    async def async_step_yaml(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        raw: Any = dict(self._entry.data)
        if user_input is not None:
            raw = user_input.get(CONF_CONFIG)
            try:
                mapping = _validate_yaml(raw)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                result = self._apply(mapping, errors)
                if result is not None:
                    return result
        return self.async_show_form(
            step_id="yaml", data_schema=_config_schema(raw), errors=errors
        )

    def _apply(
        self, mapping: dict[str, Any], errors: dict[str, str]
    ) -> Optional[FlowResult]:
        """Persist the mapping; returns a result, or None to reshow on error."""
        new_trigger = mapping[CONF_TRIGGER_ENTITY]
        updates: dict[str, Any] = {
            "data": mapping,
            "title": mapping.get(CONF_NAME) or new_trigger,
        }
        if new_trigger != self._entry.unique_id:
            if self._trigger_in_use(new_trigger):
                errors["base"] = "already_configured"
                return None
            updates["unique_id"] = new_trigger

        self.hass.config_entries.async_update_entry(self._entry, **updates)
        return self.async_create_entry(title="", data={})

    def _trigger_in_use(self, trigger_entity: str) -> bool:
        return any(
            entry.unique_id == trigger_entity and entry.entry_id != self._entry.entry_id
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )
