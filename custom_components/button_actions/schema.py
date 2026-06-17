"""Shared voluptuous schema for a single Button Actions mapping.

Used both by YAML setup (a list of mappings) and by the UI config flow (a
single mapping pasted/edited as YAML), so both paths validate identically.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CLICK_WINDOW,
    CONF_DOUBLE_CLICK_ACTION,
    CONF_FIRE_EVENTS,
    CONF_LONG_PRESS_ACTION,
    CONF_LONG_PRESS_TIME,
    CONF_MODE,
    CONF_NAME,
    CONF_PHYSICAL_ONLY,
    CONF_SINGLE_CLICK_ACTION,
    CONF_TRANSITIONS_PER_CLICK,
    CONF_TRIGGER_ENTITY,
    DEFAULT_CLICK_WINDOW,
    DEFAULT_FIRE_EVENTS,
    DEFAULT_LONG_PRESS_TIME,
    DEFAULT_MODE,
    DEFAULT_PHYSICAL_ONLY,
    MODES,
)

MAPPING_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Required(CONF_TRIGGER_ENTITY): cv.entity_id,
        vol.Optional(CONF_MODE, default=DEFAULT_MODE): vol.In(MODES),
        vol.Optional(CONF_TRANSITIONS_PER_CLICK): cv.positive_int,
        vol.Optional(CONF_CLICK_WINDOW, default=DEFAULT_CLICK_WINDOW): cv.positive_int,
        vol.Optional(
            CONF_LONG_PRESS_TIME, default=DEFAULT_LONG_PRESS_TIME
        ): cv.positive_int,
        vol.Optional(CONF_FIRE_EVENTS, default=DEFAULT_FIRE_EVENTS): cv.boolean,
        vol.Optional(CONF_PHYSICAL_ONLY, default=DEFAULT_PHYSICAL_ONLY): cv.boolean,
        vol.Optional(CONF_SINGLE_CLICK_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_DOUBLE_CLICK_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_LONG_PRESS_ACTION): cv.SCRIPT_SCHEMA,
    }
)

_TOGGLE_SERVICES = ("homeassistant.toggle", "light.toggle", "switch.toggle")


def _summarize_action(action: object) -> str:
    """Short, human description of a gesture's action sequence."""
    if not (isinstance(action, list) and action and isinstance(action[0], dict)):
        return "action"
    step = action[0]
    service = step.get("service") or step.get("action") or "action"
    target = step.get("target") if isinstance(step.get("target"), dict) else {}
    entities = target.get("entity_id")
    if entities:
        if isinstance(entities, str):
            entities = [entities]
        summary = ", ".join(entities[:2])
        if len(entities) > 2:
            summary += f" +{len(entities) - 2}"
        return summary if service in _TOGGLE_SERVICES else f"{service} → {summary}"
    suffix = "" if len(action) == 1 else f" +{len(action) - 1}"
    return f"{service}{suffix}"


def mapping_title(mapping: dict) -> str:
    """Build a one-line, emoji-decorated summary used as the config entry title.

    Example:
    ``🔘 Laurentiu (switch.shelly) · 👆 light.a, light.b · ✌️ scene.x``
    """
    name = mapping.get(CONF_NAME) or mapping[CONF_TRIGGER_ENTITY]
    head = f"🔘 {name} ({mapping[CONF_TRIGGER_ENTITY]})"
    segments = [
        f"{emoji} {_summarize_action(mapping[key])}"
        for emoji, key in (
            ("👆", CONF_SINGLE_CLICK_ACTION),
            ("✌️", CONF_DOUBLE_CLICK_ACTION),
            ("⏱️", CONF_LONG_PRESS_ACTION),
        )
        if mapping.get(key)
    ]
    return f"{head} · {' · '.join(segments)}" if segments else head
