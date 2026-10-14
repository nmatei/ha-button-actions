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
import pytest
import voluptuous as vol

from button_actions.schema import (
    apply_delays,
    delay_spec,
    expand_run_targets,
    mapping_title,
    name_from_title,
)


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
    assert mapping_title(mapping, hass) == "🔘 Kitchen Switch ⇒ ✌️ LED Kitchen"


def test_multiple_actions_use_dot_between_and_arrow_after_trigger():
    hass = _FakeHass(
        {
            "switch.salus_x": _State("Kitchen Switch"),
            "light.led_kitchen": _State("LED Kitchen"),
            "light.lamp": _State("Lamp"),
        }
    )
    mapping = {
        CONF_NAME: "Kitchen",
        CONF_TRIGGER_ENTITY: "switch.salus_x",
        CONF_SINGLE_CLICK_ACTION: _toggle("light.led_kitchen"),
        CONF_DOUBLE_CLICK_ACTION: _toggle("light.lamp"),
    }
    assert (
        mapping_title(mapping, hass)
        == "Kitchen 🔘 [ Kitchen Switch ] ⇒ 👆 LED Kitchen · ✌️ Lamp"
    )


def test_falls_back_to_entity_id_when_unknown():
    hass = _FakeHass({})  # nothing loaded
    mapping = {
        CONF_TRIGGER_ENTITY: "switch.salus_x",
        CONF_DOUBLE_CLICK_ACTION: _toggle("light.led_kitchen"),
    }
    assert mapping_title(mapping, hass) == "🔘 switch.salus_x ⇒ ✌️ light.led_kitchen"


def test_explicit_name_leads_then_button_and_trigger():
    hass = _FakeHass({"switch.salus_x": _State("Kitchen Switch")})
    mapping = {CONF_NAME: "My Custom Name", CONF_TRIGGER_ENTITY: "switch.salus_x"}
    assert mapping_title(mapping, hass) == "My Custom Name 🔘 [ Kitchen Switch ]"


def test_no_hass_uses_ids():
    mapping = {
        CONF_TRIGGER_ENTITY: "switch.salus_x",
        CONF_SINGLE_CLICK_ACTION: _toggle("light.led_kitchen"),
    }
    assert mapping_title(mapping) == "🔘 switch.salus_x ⇒ 👆 light.led_kitchen"


# --- expand_run_targets: automations are triggered, not toggled ---


def test_expand_splits_automation_out_of_mixed_toggle():
    seq = [
        {
            "service": "homeassistant.toggle",
            "target": {"entity_id": ["switch.priza_bec_tapo", "automation.test"]},
        }
    ]
    assert expand_run_targets(seq) == [
        {"service": "homeassistant.toggle", "target": {"entity_id": ["switch.priza_bec_tapo"]}},
        {"service": "automation.trigger", "target": {"entity_id": ["automation.test"]}},
    ]


def test_expand_replaces_toggle_when_only_automations():
    seq = [{"service": "homeassistant.toggle", "target": {"entity_id": "automation.test"}}]
    assert expand_run_targets(seq) == [
        {"service": "automation.trigger", "target": {"entity_id": ["automation.test"]}}
    ]


def test_expand_keeps_device_and_area_targets_on_toggle():
    seq = [
        {
            "service": "homeassistant.toggle",
            "target": {"entity_id": ["automation.test"], "area_id": "kitchen"},
        }
    ]
    assert expand_run_targets(seq) == [
        {"service": "homeassistant.toggle", "target": {"area_id": "kitchen"}},
        {"service": "automation.trigger", "target": {"entity_id": ["automation.test"]}},
    ]


def test_expand_leaves_plain_toggles_untouched():
    seq = [{"service": "light.toggle", "target": {"entity_id": ["light.led_kitchen"]}}]
    assert expand_run_targets(seq) == seq


def test_expand_ignores_non_toggle_services():
    # An explicit automation.turn_off should not be rewritten.
    seq = [{"service": "automation.turn_off", "target": {"entity_id": "automation.test"}}]
    assert expand_run_targets(seq) == seq


# --- name_from_title: inverse used when a user renames the entry ---

_TRIGGER_HASS = _FakeHass({"switch.salus_x": _State("Kitchen Switch")})


def _trigger_mapping():
    return {CONF_TRIGGER_ENTITY: "switch.salus_x"}


def test_name_from_full_title():
    title = "My Name 🔘 [ Kitchen Switch ] ⇒ ✌️ LED Kitchen"
    assert name_from_title(title, _trigger_mapping(), _TRIGGER_HASS) == "My Name"


def test_name_from_in_place_edit():
    title = "Kitchen 🔘 [ Kitchen Switch ] ⇒ ✌️ LED Kitchen"
    assert name_from_title(title, _trigger_mapping(), _TRIGGER_HASS) == "Kitchen"


def test_name_from_fresh_typed_name_without_decoration():
    # User cleared the field and typed a plain name.
    assert name_from_title("Kitchen", _trigger_mapping(), _TRIGGER_HASS) == "Kitchen"


def test_name_equal_to_trigger_clears_name():
    # Head was just the trigger and stayed that way → no custom name.
    title = "🔘 Kitchen Switch ⇒ ✌️ LED Kitchen"
    assert name_from_title(title, _trigger_mapping(), _TRIGGER_HASS) is None


def test_empty_name_clears_name():
    assert name_from_title("🔘 [ Kitchen Switch ]", _trigger_mapping(), _TRIGGER_HASS) is None


# -- sleep between actions --------------------------------------------------


def _ha_toggle(*entity_ids: str) -> list:
    return [{"service": "homeassistant.toggle", "target": {"entity_id": list(entity_ids)}}]


def _one(service: str, entity_id: str) -> dict:
    return {"service": service, "target": {"entity_id": [entity_id]}}


def _sleep(ms: int) -> dict:
    return {"delay": {"milliseconds": ms}}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        (300, 300),
        ("300", 300),
        ("100, 200", [100, 200]),
        ("0,200,400", [0, 200, 400]),
        ("300,", [300]),
        ([100, "200"], [100, 200]),
    ],
)
def test_delay_spec_parses(raw, expected):
    assert delay_spec(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "100,x", -5, "10,-1", True])
def test_delay_spec_rejects_invalid(raw):
    with pytest.raises(vol.Invalid):
        delay_spec(raw)


def test_no_delay_leaves_sequence_untouched():
    seq = _ha_toggle("light.a", "light.b")
    assert apply_delays(seq, None) is seq
    assert apply_delays(seq, 0) is seq
    assert apply_delays(seq, [0, 0]) is seq


def test_single_number_is_gap_between_actions():
    seq = _ha_toggle("light.a", "light.b", "light.c")
    t = "homeassistant.toggle"
    assert apply_delays(seq, 300) == [
        _one(t, "light.a"),
        _sleep(300),
        _one(t, "light.b"),
        _sleep(300),
        _one(t, "light.c"),
    ]


def test_list_is_sleep_before_each_action_and_cycles():
    seq = _ha_toggle("light.a", "light.b", "light.c")
    t = "homeassistant.toggle"
    assert apply_delays(seq, [100, 200]) == [
        _sleep(100),
        _one(t, "light.a"),
        _sleep(200),
        _one(t, "light.b"),
        _sleep(100),
        _one(t, "light.c"),
    ]


def test_zero_entries_in_list_add_no_sleep():
    seq = _ha_toggle("light.a", "light.b")
    t = "homeassistant.toggle"
    assert apply_delays(seq, [0, 500]) == [
        _one(t, "light.a"),
        _sleep(500),
        _one(t, "light.b"),
    ]


def test_delays_apply_to_triggered_automations_too():
    seq = expand_run_targets(_ha_toggle("light.a", "automation.x", "automation.y"))
    assert apply_delays(seq, 100) == [
        _one("homeassistant.toggle", "light.a"),
        _sleep(100),
        _one("automation.trigger", "automation.x"),
        _sleep(100),
        _one("automation.trigger", "automation.y"),
    ]


def test_device_and_area_targets_are_split():
    seq = [
        {
            "service": "light.toggle",
            "target": {"entity_id": "light.a", "device_id": ["d1"], "area_id": ["kitchen"]},
        }
    ]
    assert apply_delays(seq, 50) == [
        {"service": "light.toggle", "target": {"entity_id": ["light.a"]}},
        _sleep(50),
        {"service": "light.toggle", "target": {"device_id": ["d1"]}},
        _sleep(50),
        {"service": "light.toggle", "target": {"area_id": ["kitchen"]}},
    ]


def test_non_toggle_steps_count_as_one_action_each():
    scene = {"service": "scene.turn_on", "target": {"entity_id": ["scene.a", "scene.b"]}}
    script = {"service": "script.x"}
    assert apply_delays([scene, script], 200) == [scene, _sleep(200), script]
