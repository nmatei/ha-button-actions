"""Shared voluptuous schema for a single Button Actions mapping.

Used both by YAML setup (a list of mappings) and by the UI config flow (a
single mapping pasted/edited as YAML), so both paths validate identically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.helpers import config_validation as cv

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

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

# Title head format: ``{name} 🔘 [ {trigger} ]`` so the entry leads with the
# user's name (or ``🔘 {trigger}`` when no name is set). These markers are shared
# by ``mapping_title`` and its inverse, ``name_from_title``, so the round-trip
# stays consistent.
_BUTTON = "🔘"
_TITLE_PREFIX = f"{_BUTTON} "  # no-name head: ``🔘 {trigger}``
_TRIGGER_OPEN = " [ "
_TRIGGER_CLOSE = " ]"
_TRIGGER_SEP = " ⇒ "  # trigger ⇒ its gesture actions
_ACTION_SEP = " · "  # between individual gesture actions


def _entity_name(hass: "HomeAssistant | None", entity_id: str) -> str:
    """Friendly name for an entity, falling back to its id."""
    if hass is not None:
        state = hass.states.get(entity_id)
        if state:
            name = state.attributes.get("friendly_name")
            if name:
                return name
    return entity_id


def _summarize_action(action: object, hass: "HomeAssistant | None" = None) -> str:
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
        names = [_entity_name(hass, entity_id) for entity_id in entities[:2]]
        summary = ", ".join(names)
        if len(entities) > 2:
            summary += f" +{len(entities) - 2}"
        return summary if service in _TOGGLE_SERVICES else f"{service} → {summary}"
    suffix = "" if len(action) == 1 else f" +{len(action) - 1}"
    return f"{service}{suffix}"


def mapping_title(mapping: dict, hass: "HomeAssistant | None" = None) -> str:
    """Build a one-line, emoji-decorated summary used as the config entry title.

    Entity ids are shown as their friendly names when ``hass`` is provided and
    the entity is loaded, falling back to the raw id otherwise.

    Example:
    ``Laurentiu 🔘 [ Shelly Switch ] ⇒ 👆 Light A, Light B · ✌️ scene.x``
    """
    trigger = _entity_name(hass, mapping[CONF_TRIGGER_ENTITY])
    name = mapping.get(CONF_NAME)
    if name:
        head = f"{name} {_BUTTON}{_TRIGGER_OPEN}{trigger}{_TRIGGER_CLOSE}"
    else:
        head = f"{_TITLE_PREFIX}{trigger}"
    segments = [
        f"{emoji} {_summarize_action(mapping[key], hass)}"
        for emoji, key in (
            ("👆", CONF_SINGLE_CLICK_ACTION),
            ("✌️", CONF_DOUBLE_CLICK_ACTION),
            ("⏱️", CONF_LONG_PRESS_ACTION),
        )
        if mapping.get(key)
    ]
    return f"{head}{_TRIGGER_SEP}{_ACTION_SEP.join(segments)}" if segments else head


def name_from_title(
    title: str, mapping: dict, hass: "HomeAssistant | None" = None
) -> str | None:
    """Recover the user-facing name from a (possibly hand-edited) entry title.

    Inverse of :func:`mapping_title`'s head. HA's "edit name" dialog edits the
    whole title, so when a user renames an entry we reinterpret what they typed
    as the configured ``name``. Returns ``None`` when the title carries no
    custom name (i.e. it's just the trigger), so the caller can clear it.
    """
    # Keep only the head; drop any gesture summary.
    head = title.split(_TRIGGER_SEP, 1)[0]
    if _BUTTON in head:
        # ``{name} 🔘 [ {trigger} ]`` → the name is everything before the 🔘.
        # ``🔘 {trigger}`` (no name) yields an empty leading part → None.
        return head.split(_BUTTON, 1)[0].strip() or None
    # No 🔘 marker → the user cleared the decoration and typed a plain name.
    # Treat it as the new name unless it still equals the trigger's display.
    name = head.strip()
    trigger = _entity_name(hass, mapping[CONF_TRIGGER_ENTITY])
    if not name or name == trigger:
        return None
    return name
