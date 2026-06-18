"""Unit tests for mapping_title friendly-name rendering.

These run without a Home Assistant runtime; conftest stubs the voluptuous and
config_validation deps so ``schema`` imports, and a fake hass provides states.
"""

from __future__ import annotations

from button_actions.const import (
    CONF_DOUBLE_CLICK_ACTION,
    CONF_NAME,
    CONF_SINGLE_CLICK_ACTION,
    CONF_TRIGGER_ENTITY,
)
from button_actions.schema import mapping_title, name_from_title


class _State:
    def __init__(self, friendly_name: str | None = None) -> None:
        self.attributes: dict = {}
        if friendly_name is not None:
            self.attributes["friendly_name"] = friendly_name


class _FakeStates:
    def __init__(self, states: dict) -> None:
        self._states = states

    def get(self, entity_id: str):
        return self._states.get(entity_id)


class _FakeHass:
    def __init__(self, states: dict) -> None:
        self.states = _FakeStates(states)


def _toggle(entity_id: str) -> list:
    return [{"service": "light.toggle", "target": {"entity_id": entity_id}}]


def test_uses_friendly_names_when_available():
    hass = _FakeHass(
        {
            "switch.salus_x": _State("Kitchen Switch"),
            "light.led_kitchen": _State("LED Kitchen"),
        }
    )
    mapping = {
        CONF_TRIGGER_ENTITY: "switch.salus_x",
        CONF_DOUBLE_CLICK_ACTION: _toggle("light.led_kitchen"),
    }
    assert mapping_title(mapping, hass) == "🔘 Kitchen Switch · ✌️ LED Kitchen"


def test_falls_back_to_entity_id_when_unknown():
    hass = _FakeHass({})  # nothing loaded
    mapping = {
        CONF_TRIGGER_ENTITY: "switch.salus_x",
        CONF_DOUBLE_CLICK_ACTION: _toggle("light.led_kitchen"),
    }
    assert mapping_title(mapping, hass) == "🔘 switch.salus_x · ✌️ light.led_kitchen"


def test_explicit_name_keeps_trigger_in_brackets():
    hass = _FakeHass({"switch.salus_x": _State("Kitchen Switch")})
    mapping = {CONF_NAME: "My Custom Name", CONF_TRIGGER_ENTITY: "switch.salus_x"}
    assert mapping_title(mapping, hass) == "🔘 My Custom Name [ Kitchen Switch ]"


def test_no_hass_uses_ids():
    mapping = {
        CONF_TRIGGER_ENTITY: "switch.salus_x",
        CONF_SINGLE_CLICK_ACTION: _toggle("light.led_kitchen"),
    }
    assert mapping_title(mapping) == "🔘 switch.salus_x · 👆 light.led_kitchen"


# --- name_from_title: inverse used when a user renames the entry ---

_TRIGGER_HASS = _FakeHass({"switch.salus_x": _State("Kitchen Switch")})


def _trigger_mapping():
    return {CONF_TRIGGER_ENTITY: "switch.salus_x"}


def test_name_from_full_title():
    title = "🔘 My Name [ Kitchen Switch ] · ✌️ LED Kitchen"
    assert name_from_title(title, _trigger_mapping(), _TRIGGER_HASS) == "My Name"


def test_name_from_in_place_edit():
    title = "🔘 Kitchen [ Kitchen Switch ] · ✌️ LED Kitchen"
    assert name_from_title(title, _trigger_mapping(), _TRIGGER_HASS) == "Kitchen"


def test_name_from_fresh_typed_name_without_brackets():
    # User cleared the field and typed a plain name.
    assert name_from_title("Kitchen", _trigger_mapping(), _TRIGGER_HASS) == "Kitchen"


def test_name_equal_to_trigger_clears_name():
    # Head was just the trigger and stayed that way → no custom name.
    title = "🔘 Kitchen Switch · ✌️ LED Kitchen"
    assert name_from_title(title, _trigger_mapping(), _TRIGGER_HASS) is None


def test_empty_name_clears_name():
    assert name_from_title("🔘  [ Kitchen Switch ]", _trigger_mapping(), _TRIGGER_HASS) is None
