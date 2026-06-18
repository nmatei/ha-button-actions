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
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_NAME,
    DATA_CONTROLLERS,
    DATA_YAML_CONFIG,
    DOMAIN,
    SERVICE_RELOAD,
)
from .controller import ButtonActionController
from .schema import MAPPING_SCHEMA, mapping_title, name_from_title

_LOGGER = logging.getLogger(__name__)

DATA_YAML_CONTROLLERS = "yaml_controllers"

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

    # Refresh every entry's friendly-name title — including disabled ones, which
    # never run async_setup_entry. At cold start the trigger/target entities
    # aren't loaded yet (titles would fall back to raw ids), so defer until HA
    # has started; if we're already running, do it now.
    @callback
    def _refresh_all_titles(_event: Any = None) -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            mapping = {**entry.data, **entry.options}
            _async_refresh_title(hass, entry, mapping)

    if hass.is_running:
        _refresh_all_titles()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _refresh_all_titles)

    return True


@callback
def _async_refresh_title(
    hass: HomeAssistant, entry: ConfigEntry, mapping: dict
) -> None:
    """Set the entry title to a fresh, friendly-name summary of the mapping."""
    title = mapping_title(mapping, hass)
    if entry.title != title:
        hass.config_entries.async_update_entry(entry, title=title)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a UI-configured mapping from a config entry."""
    data = _domain_data(hass)
    mapping = {**entry.data, **entry.options}

    # Cold-start titles are refreshed centrally in async_setup once HA has
    # started (entities loaded). Here we only need to handle entries set up
    # while HA is already running (a freshly added or reloaded entry), whose
    # target entities are present, so the names resolve immediately.
    if hass.is_running:
        _async_refresh_title(hass, entry, mapping)

    controller = ButtonActionController(hass, mapping)
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
    """React to entry updates: option changes (reload) and manual renames.

    HA's "edit name" dialog edits the whole title, so a manual rename arrives
    here as a title that no longer matches our generated summary. We reinterpret
    what the user typed as the configured ``name`` and regenerate the full
    title; that re-entry then takes the reload path below.
    """
    mapping = {**entry.data, **entry.options}
    if entry.title != mapping_title(mapping, hass):
        new_name = name_from_title(entry.title, mapping, hass)
        data = dict(entry.data)
        if new_name:
            data[CONF_NAME] = new_name
        else:
            data.pop(CONF_NAME, None)
        regenerated = mapping_title({**data, **entry.options}, hass)
        hass.config_entries.async_update_entry(entry, data=data, title=regenerated)
        return

    await hass.config_entries.async_reload(entry.entry_id)
