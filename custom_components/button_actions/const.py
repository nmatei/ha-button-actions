"""Constants for the Button Actions integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "button_actions"

# Config keys -----------------------------------------------------------------
CONF_NAME: Final = "name"
CONF_TRIGGER_ENTITY: Final = "trigger_entity"
CONF_MODE: Final = "mode"
CONF_CLICK_WINDOW: Final = "click_window"
CONF_LONG_PRESS_TIME: Final = "long_press_time"
CONF_FIRE_EVENTS: Final = "fire_events"
CONF_PHYSICAL_ONLY: Final = "physical_only"
CONF_TRANSITIONS_PER_CLICK: Final = "transitions_per_click"

CONF_SINGLE_CLICK_ACTION: Final = "single_click_action"
CONF_DOUBLE_CLICK_ACTION: Final = "double_click_action"
CONF_LONG_PRESS_ACTION: Final = "long_press_action"

# Input modes -----------------------------------------------------------------
MODE_MOMENTARY: Final = "momentary"
MODE_TOGGLE: Final = "toggle"
MODES: Final = (MODE_MOMENTARY, MODE_TOGGLE)

# How many state transitions make up a single press, per mode.
TRANSITIONS_PER_CLICK_BY_MODE: Final = {
    MODE_MOMENTARY: 2,  # OFF -> ON -> OFF
    MODE_TOGGLE: 1,  # OFF -> ON (state holds)
}

# Gestures --------------------------------------------------------------------
GESTURE_SINGLE: Final = "single_click"
GESTURE_DOUBLE: Final = "double_click"
GESTURE_LONG: Final = "long_press"

# Map a gesture to the number of presses it represents.
GESTURE_CLICK_COUNT: Final = {
    GESTURE_SINGLE: 1,
    GESTURE_DOUBLE: 2,
}

# Defaults --------------------------------------------------------------------
DEFAULT_MODE: Final = MODE_TOGGLE
DEFAULT_CLICK_WINDOW: Final = 600  # ms
DEFAULT_LONG_PRESS_TIME: Final = 1200  # ms
DEFAULT_FIRE_EVENTS: Final = False
DEFAULT_PHYSICAL_ONLY: Final = True

# Events ----------------------------------------------------------------------
EVENT_GESTURE: Final = "button_actions_gesture"

# Event / attribute data keys
ATTR_ENTITY_ID: Final = "entity_id"
ATTR_GESTURE: Final = "gesture"
ATTR_NAME: Final = "name"

# Services --------------------------------------------------------------------
SERVICE_RELOAD: Final = "reload"

# hass.data layout ------------------------------------------------------------
DATA_CONTROLLERS: Final = "controllers"
DATA_YAML_CONFIG: Final = "yaml_config"
