"""Config and options flow for Button Actions.

A mapping can be entered two ways, and you can switch between them at any time
(a checkbox in each view jumps to the other, carrying your current values):

* **Guided** — friendly fields (trigger entity, mode, timeouts) and a target
  picker per gesture (toggle these lights).
* **YAML** — the whole mapping as one YAML object, same shape as the examples,
  for anything beyond a toggle (scenes, scripts, templates).

Both paths produce the same normalized mapping (validated by MAPPING_SCHEMA).
Actions that aren't a simple toggle are preserved when switching to the guided
view (they just aren't shown as a target picker) and remain editable in YAML.
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
from .schema import MAPPING_SCHEMA, mapping_title

# The single field that holds the whole mapping in the YAML step.
CONF_CONFIG = "config"
# Checkboxes that switch between views.
SWITCH_TO_YAML = "edit_as_yaml"
SWITCH_TO_FORM = "edit_with_fields"

# (action key, UI-only target-picker key) per gesture.
_GESTURES = (
    (CONF_SINGLE_CLICK_ACTION, "single_click_targets"),
    (CONF_DOUBLE_CLICK_ACTION, "double_click_targets"),
    (CONF_LONG_PRESS_ACTION, "long_press_targets"),
)

# Services treated as a simple toggle for round-tripping to the target picker.
_TOGGLE_SERVICES = ("homeassistant.toggle", "light.toggle", "switch.toggle")

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


def _targets_from_action(action: Any) -> dict[str, Any]:
    """If an action is a single toggle with a target, return that target."""
    if isinstance(action, list) and len(action) == 1 and isinstance(action[0], dict):
        step = action[0]
        service = step.get("service") or step.get("action")
        target = step.get("target")
        if service in _TOGGLE_SERVICES and isinstance(target, dict):
            return target
    return {}


def _form_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Guided multi-field schema, prefilled from a mapping-like ``defaults``."""

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
        target_default = defaults.get(target_key)
        if not _has_targets(target_default):
            target_default = _targets_from_action(defaults.get(action_key))
        schema[
            vol.Optional(target_key, default=target_default or {})
        ] = selector.TargetSelector()

    schema[vol.Optional(SWITCH_TO_YAML, default=False)] = selector.BooleanSelector()
    return vol.Schema(schema)


def _yaml_schema(default_value: Any) -> vol.Schema:
    """Single whole-mapping YAML field, plus a switch-to-guided checkbox."""
    return vol.Schema(
        {
            vol.Required(CONF_CONFIG, default=default_value): selector.ObjectSelector(),
            vol.Optional(SWITCH_TO_FORM, default=False): selector.BooleanSelector(),
        }
    )


def _merge_form(user_input: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Build a (loose) mapping draft from guided input, layered over ``base``.

    Targets become a toggle action; gestures left empty keep whatever action the
    base mapping already had (so non-toggle actions survive a view switch).
    """
    draft: dict[str, Any] = {
        CONF_MODE: user_input.get(CONF_MODE, base.get(CONF_MODE, DEFAULT_MODE)),
        CONF_CLICK_WINDOW: int(
            user_input.get(CONF_CLICK_WINDOW, base.get(CONF_CLICK_WINDOW, DEFAULT_CLICK_WINDOW))
        ),
        CONF_LONG_PRESS_TIME: int(
            user_input.get(
                CONF_LONG_PRESS_TIME, base.get(CONF_LONG_PRESS_TIME, DEFAULT_LONG_PRESS_TIME)
            )
        ),
        CONF_FIRE_EVENTS: user_input.get(
            CONF_FIRE_EVENTS, base.get(CONF_FIRE_EVENTS, DEFAULT_FIRE_EVENTS)
        ),
    }
    name = (user_input.get(CONF_NAME) or "").strip()
    if name:
        draft[CONF_NAME] = name
    trigger = user_input.get(CONF_TRIGGER_ENTITY)
    if trigger:
        draft[CONF_TRIGGER_ENTITY] = trigger

    for action_key, target_key in _GESTURES:
        target = user_input.get(target_key)
        if _has_targets(target):
            draft[action_key] = [
                {"service": "homeassistant.toggle", "target": target}
            ]
        elif base.get(action_key):
            draft[action_key] = base[action_key]

    return draft


def _validate_yaml(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise vol.Invalid("Expected a single mapping (a YAML object)")
    return MAPPING_SCHEMA(raw)


class ButtonActionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        self._draft: dict[str, Any] = {}
        return self.async_show_menu(step_id="user", menu_options=["form", "yaml"])

    async def async_step_form(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(user_input)
            switch = data.pop(SWITCH_TO_YAML, False)
            self._draft = _merge_form(data, self._draft)
            if switch:
                return await self.async_step_yaml()
            try:
                mapping = MAPPING_SCHEMA(self._draft)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                return await self._create(mapping)
        defaults = user_input if user_input is not None else self._draft
        return self.async_show_form(
            step_id="form", data_schema=_form_schema(defaults), errors=errors
        )

    async def async_step_yaml(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            switch = user_input.get(SWITCH_TO_FORM, False)
            raw = user_input.get(CONF_CONFIG)
            self._draft = raw if isinstance(raw, dict) else {}
            if switch:
                return await self.async_step_form()
            try:
                mapping = _validate_yaml(raw)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                return await self._create(mapping)
            default = raw
        else:
            default = self._draft or TEMPLATE_MAPPING
        return self.async_show_form(
            step_id="yaml", data_schema=_yaml_schema(default), errors=errors
        )

    async def _create(self, mapping: dict[str, Any]) -> FlowResult:
        await self.async_set_unique_id(mapping[CONF_TRIGGER_ENTITY])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=mapping_title(mapping), data=mapping)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return ButtonActionsOptionsFlow(entry)


class ButtonActionsOptionsFlow(OptionsFlow):
    """Edit a mapping via guided fields or whole-mapping YAML."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._draft: dict[str, Any] = dict(entry.data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(step_id="init", menu_options=["form", "yaml"])

    async def async_step_form(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(user_input)
            switch = data.pop(SWITCH_TO_YAML, False)
            self._draft = _merge_form(data, self._draft)
            if switch:
                return await self.async_step_yaml()
            try:
                mapping = MAPPING_SCHEMA(self._draft)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                result = self._apply(mapping, errors)
                if result is not None:
                    return result
        defaults = user_input if user_input is not None else self._draft
        return self.async_show_form(
            step_id="form", data_schema=_form_schema(defaults), errors=errors
        )

    async def async_step_yaml(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            switch = user_input.get(SWITCH_TO_FORM, False)
            raw = user_input.get(CONF_CONFIG)
            self._draft = raw if isinstance(raw, dict) else {}
            if switch:
                return await self.async_step_form()
            try:
                mapping = _validate_yaml(raw)
            except vol.Invalid:
                errors["base"] = "invalid_config"
            else:
                result = self._apply(mapping, errors)
                if result is not None:
                    return result
            default = raw
        else:
            default = self._draft
        return self.async_show_form(
            step_id="yaml", data_schema=_yaml_schema(default), errors=errors
        )

    def _apply(
        self, mapping: dict[str, Any], errors: dict[str, str]
    ) -> Optional[FlowResult]:
        """Persist the mapping; returns a result, or None to reshow on error."""
        new_trigger = mapping[CONF_TRIGGER_ENTITY]
        updates: dict[str, Any] = {
            "data": mapping,
            "title": mapping_title(mapping),
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
