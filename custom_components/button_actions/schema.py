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
    CONF_SINGLE_CLICK_ACTION,
    CONF_TRANSITIONS_PER_CLICK,
    CONF_TRIGGER_ENTITY,
    DEFAULT_CLICK_WINDOW,
    DEFAULT_FIRE_EVENTS,
    DEFAULT_LONG_PRESS_TIME,
    DEFAULT_MODE,
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
        vol.Optional(CONF_SINGLE_CLICK_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_DOUBLE_CLICK_ACTION): cv.SCRIPT_SCHEMA,
        vol.Optional(CONF_LONG_PRESS_ACTION): cv.SCRIPT_SCHEMA,
    }
)
