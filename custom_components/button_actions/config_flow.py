"""Config and options flow for Button Actions.

The UI flow covers the common case: pick a trigger entity, the input mode and
timing, and a set of target entities to toggle for each gesture. Arbitrary
action sequences (scenes, scripts, choose, templates) remain YAML-only.
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
    CONF_CLICK_WINDOW,
    CONF_DOUBLE_CLICK_ACTION,
    CONF_DOUBLE_CLICK_TARGETS,
    CONF_FIRE_EVENTS,
    CONF_LONG_PRESS_ACTION,
    CONF_LONG_PRESS_TARGETS,
    CONF_LONG_PRESS_TIME,
    CONF_MODE,
    CONF_NAME,
    CONF_SINGLE_CLICK_ACTION,
    CONF_SINGLE_CLICK_TARGETS,
    CONF_TRIGGER_ENTITY,
    DEFAULT_CLICK_WINDOW,
    DEFAULT_FIRE_EVENTS,
    DEFAULT_LONG_PRESS_TIME,
    DEFAULT_MODE,
    DOMAIN,
    MODES,
)

# Pairs of (UI target key, action key) so we can build actions from selections.
_TARGET_TO_ACTION = (
    (CONF_SINGLE_CLICK_TARGETS, CONF_SINGLE_CLICK_ACTION),
    (CONF_DOUBLE_CLICK_TARGETS, CONF_DOUBLE_CLICK_ACTION),
    (CONF_LONG_PRESS_TARGETS, CONF_LONG_PRESS_ACTION),
)


def _has_targets(target: Any) -> bool:
    if not isinstance(target, dict):
        return False
    return any(target.get(key) for key in ("entity_id", "device_id", "area_id"))


def _build_data(user_input: dict[str, Any]) -> dict[str, Any]:
    """Turn raw form input into stored entry data, including action sequences."""
    data: dict[str, Any] = {
        CONF_NAME: user_input.get(CONF_NAME),
        CONF_TRIGGER_ENTITY: user_input[CONF_TRIGGER_ENTITY],
        CONF_MODE: user_input.get(CONF_MODE, DEFAULT_MODE),
        CONF_CLICK_WINDOW: int(user_input.get(CONF_CLICK_WINDOW, DEFAULT_CLICK_WINDOW)),
        CONF_LONG_PRESS_TIME: int(
            user_input.get(CONF_LONG_PRESS_TIME, DEFAULT_LONG_PRESS_TIME)
        ),
        CONF_FIRE_EVENTS: user_input.get(CONF_FIRE_EVENTS, DEFAULT_FIRE_EVENTS),
    }

    for target_key, action_key in _TARGET_TO_ACTION:
        target = user_input.get(target_key)
        action = user_input.get(action_key)

        if action:
            # An explicit YAML action sequence wins over the toggle targets.
            data[action_key] = action
            if _has_targets(target):
                data[target_key] = target
        elif _has_targets(target):
            data[target_key] = target
            data[action_key] = [
                {"service": "homeassistant.toggle", "target": target}
            ]
    return data


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the form schema, prefilling from ``defaults``."""

    def default(key: str, fallback: Any) -> Any:
        value = defaults.get(key, fallback)
        return value if value is not None else fallback

    schema: dict[Any, Any] = {
        vol.Optional(
            CONF_NAME, default=default(CONF_NAME, "")
        ): selector.TextSelector(),
        vol.Required(
            CONF_TRIGGER_ENTITY,
            default=default(CONF_TRIGGER_ENTITY, vol.UNDEFINED),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["switch", "binary_sensor", "input_boolean"])
        ),
        vol.Optional(
            CONF_MODE, default=default(CONF_MODE, DEFAULT_MODE)
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(MODES),
                translation_key="mode",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(
            CONF_CLICK_WINDOW, default=default(CONF_CLICK_WINDOW, DEFAULT_CLICK_WINDOW)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=100, max=3000, step=50, unit_of_measurement="ms"
            )
        ),
        vol.Optional(
            CONF_LONG_PRESS_TIME,
            default=default(CONF_LONG_PRESS_TIME, DEFAULT_LONG_PRESS_TIME),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=300, max=5000, step=50, unit_of_measurement="ms"
            )
        ),
        vol.Optional(
            CONF_FIRE_EVENTS, default=default(CONF_FIRE_EVENTS, DEFAULT_FIRE_EVENTS)
        ): selector.BooleanSelector(),
    }

    for target_key, action_key in _TARGET_TO_ACTION:
        schema[
            vol.Optional(target_key, default=defaults.get(target_key, {}))
        ] = selector.TargetSelector()

        # Advanced: a raw YAML action sequence. When editing, it is prefilled
        # with the stored action so it can be copied/edited. Overrides targets.
        action_default = defaults.get(action_key)
        action_marker = (
            vol.Optional(action_key, default=action_default)
            if action_default
            else vol.Optional(action_key)
        )
        schema[action_marker] = selector.ObjectSelector()

    return vol.Schema(schema)


class ButtonActionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_TRIGGER_ENTITY])
            self._abort_if_unique_id_configured()
            data = _build_data(user_input)
            title = data.get(CONF_NAME) or data[CONF_TRIGGER_ENTITY]
            return self.async_create_entry(title=title, data=data)

        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return ButtonActionsOptionsFlow(entry)


class ButtonActionsOptionsFlow(OptionsFlow):
    """Allow editing a mapping after creation."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            new_trigger = user_input[CONF_TRIGGER_ENTITY]
            data = _build_data(user_input)
            updates: dict[str, Any] = {
                "data": data,
                "title": data.get(CONF_NAME) or new_trigger,
            }
            if new_trigger != self._entry.unique_id:
                # The trigger entity is the unique id; keep them in sync and
                # guard against colliding with another configured mapping.
                if self._trigger_in_use(new_trigger):
                    errors[CONF_TRIGGER_ENTITY] = "already_configured"
                else:
                    updates["unique_id"] = new_trigger

            if not errors:
                self.hass.config_entries.async_update_entry(self._entry, **updates)
                return self.async_create_entry(title="", data={})

        defaults = {**self._entry.data, **(user_input or {})}
        return self.async_show_form(
            step_id="init", data_schema=_schema(defaults), errors=errors
        )

    def _trigger_in_use(self, trigger_entity: str) -> bool:
        return any(
            entry.unique_id == trigger_entity and entry.entry_id != self._entry.entry_id
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )
