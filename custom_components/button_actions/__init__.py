"""The Button Actions integration.

Turns ON/OFF state changes of a trigger entity into button gestures
(single / double click, long press) and maps them to actions and/or events.

Supports both YAML configuration (a list under ``button_actions:``) and the UI
config flow. Both paths build the same :class:`ButtonActionController`.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.typing import ConfigType

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
    DATA_CONTROLLERS,
    DATA_YAML_CONFIG,
    DEFAULT_CLICK_WINDOW,
    DEFAULT_FIRE_EVENTS,
    DEFAULT_LONG_PRESS_TIME,
    DEFAULT_MODE,
    DOMAIN,
    MODES,
    SERVICE_RELOAD,
)
from .controller import ButtonActionController

_LOGGER = logging.getLogger(__name__)

DATA_YAML_CONTROLLERS = "yaml_controllers"

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

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [MAPPING_SCHEMA])},
    extra=vol.ALLOW_EXTRA,
)


@callback
def _domain_data(hass: HomeAssistant) -> dict[str, Any]:
    return hass.data.setdefault(
        DOMAIN, {DATA_CONTROLLERS: {}, DATA_YAML_CONTROLLERS: []}
    )


@callback
def _setup_yaml_controllers(hass: HomeAssistant, mappings: list[dict]) -> None:
    """Build controllers for every YAML mapping."""
    data = _domain_data(hass)
    for mapping in mappings:
        controller = ButtonActionController(hass, dict(mapping))
        controller.async_setup()
        data[DATA_YAML_CONTROLLERS].append(controller)


@callback
def _teardown_yaml_controllers(hass: HomeAssistant) -> None:
    data = _domain_data(hass)
    for controller in data[DATA_YAML_CONTROLLERS]:
        controller.async_unload()
    data[DATA_YAML_CONTROLLERS] = []


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up YAML-configured mappings and register the reload service."""
    data = _domain_data(hass)
    mappings = config.get(DOMAIN, [])
    data[DATA_YAML_CONFIG] = mappings
    _setup_yaml_controllers(hass, mappings)

    async def _handle_reload(call: ServiceCall) -> None:
        reloaded = await async_integration_yaml_config(hass, DOMAIN)
        new_mappings = (reloaded or {}).get(DOMAIN, [])
        _teardown_yaml_controllers(hass)
        data[DATA_YAML_CONFIG] = new_mappings
        _setup_yaml_controllers(hass, new_mappings)
        _LOGGER.info("Reloaded %d button_actions YAML mapping(s)", len(new_mappings))

    hass.services.async_register(DOMAIN, SERVICE_RELOAD, _handle_reload)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a UI-configured mapping from a config entry."""
    data = _domain_data(hass)
    controller = ButtonActionController(hass, {**entry.data, **entry.options})
    controller.async_setup()
    data[DATA_CONTROLLERS][entry.entry_id] = controller

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down a UI-configured mapping."""
    data = _domain_data(hass)
    controller = data[DATA_CONTROLLERS].pop(entry.entry_id, None)
    if controller is not None:
        controller.async_unload()
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
