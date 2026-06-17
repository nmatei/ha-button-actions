"""Runtime controller that binds a trigger entity to gesture actions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Optional

import voluptuous as vol

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.helpers.script import Script

from .const import (
    ATTR_ENTITY_ID,
    ATTR_GESTURE,
    ATTR_NAME,
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
    DOMAIN,
    EVENT_GESTURE,
    GESTURE_DOUBLE,
    GESTURE_LONG,
    GESTURE_SINGLE,
    TRANSITIONS_PER_CLICK_BY_MODE,
)
from .gesture import GestureDetector

_LOGGER = logging.getLogger(__name__)

# Maps each gesture to the config key holding its action sequence.
_ACTION_KEYS = {
    GESTURE_SINGLE: CONF_SINGLE_CLICK_ACTION,
    GESTURE_DOUBLE: CONF_DOUBLE_CLICK_ACTION,
    GESTURE_LONG: CONF_LONG_PRESS_ACTION,
}


class ButtonActionController:
    """Watch one trigger entity, detect gestures, and run their actions."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self._config = config
        self._name: str = config.get(CONF_NAME) or config[CONF_TRIGGER_ENTITY]
        self._entity_id: str = config[CONF_TRIGGER_ENTITY]
        self._fire_events: bool = config.get(CONF_FIRE_EVENTS, DEFAULT_FIRE_EVENTS)
        self._physical_only: bool = config.get(
            CONF_PHYSICAL_ONLY, DEFAULT_PHYSICAL_ONLY
        )

        mode = config.get(CONF_MODE, DEFAULT_MODE)
        self._transitions_per_click: int = config.get(
            CONF_TRANSITIONS_PER_CLICK
        ) or TRANSITIONS_PER_CLICK_BY_MODE.get(mode, 2)

        self._click_window_s = config.get(CONF_CLICK_WINDOW, DEFAULT_CLICK_WINDOW) / 1000
        self._long_press_time_s = (
            config.get(CONF_LONG_PRESS_TIME, DEFAULT_LONG_PRESS_TIME) / 1000
        )

        # Build a Script per gesture that has an action sequence configured.
        # The sequence must be normalized by cv.SCRIPT_SCHEMA before Script can
        # run it (this turns `service:`/`action:` into the form the executor
        # expects). YAML config is already validated; UI/legacy entries may hold
        # raw dicts, so we (idempotently) validate here too.
        self._scripts: dict[str, Script] = {}
        for gesture, key in _ACTION_KEYS.items():
            sequence = config.get(key)
            if not sequence:
                continue
            try:
                sequence = cv.SCRIPT_SCHEMA(sequence)
            except vol.Invalid as err:
                _LOGGER.error(
                    "button_actions '%s' has an invalid %s action, skipping: %s",
                    self._name,
                    gesture,
                    err,
                )
                continue
            self._scripts[gesture] = Script(
                hass,
                sequence,
                f"{self._name} {gesture}",
                DOMAIN,
            )

        # A gesture is active if it has an action or events are enabled.
        active = set(self._scripts)
        if self._fire_events:
            active |= {GESTURE_SINGLE, GESTURE_DOUBLE, GESTURE_LONG}

        # Long press is detected by the input being *held* past a threshold.
        # That only works when the input returns to rest after a press
        # (momentary). In toggle mode the state simply holds after a single
        # press, so arming a hold timer would turn every single click into a
        # long press — never arm it there.
        if self._transitions_per_click < 2:
            if GESTURE_LONG in self._scripts:
                _LOGGER.warning(
                    "button_actions '%s': long_press is not supported in toggle "
                    "mode (the input has no rest state); its action is ignored",
                    self._name,
                )
            active.discard(GESTURE_LONG)

        self._detector = GestureDetector(
            transitions_per_click=self._transitions_per_click,
            click_window_s=self._click_window_s,
            long_press_time_s=self._long_press_time_s,
            active_gestures=active,
            on_gesture=self._on_gesture,
            schedule=self._schedule,
        )

        self._unsub_state: Optional[Callable[[], None]] = None

    @callback
    def async_setup(self) -> None:
        """Start listening to the trigger entity's state changes."""
        self._unsub_state = async_track_state_change_event(
            self.hass, [self._entity_id], self._handle_state_event
        )
        _LOGGER.debug(
            "button_actions controller '%s' watching %s (active: %s)",
            self._name,
            self._entity_id,
            ", ".join(sorted(self._detector_active())) or "none",
        )

    @callback
    def async_unload(self) -> None:
        """Stop listening and cancel any pending timers."""
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        self._detector.cancel()

    # -- internals ------------------------------------------------------------

    def _detector_active(self) -> set[str]:
        active = set(self._scripts)
        if self._fire_events:
            active |= {GESTURE_SINGLE, GESTURE_DOUBLE, GESTURE_LONG}
        return active

    @staticmethod
    def _as_bool(state: str) -> Optional[bool]:
        if state == STATE_ON:
            return True
        if state == STATE_OFF:
            return False
        return None

    @callback
    def _handle_state_event(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        new_on = self._as_bool(new_state.state)
        if new_on is None:
            # Ignore unavailable/unknown and any non on/off state.
            return

        old_state = event.data.get("old_state")
        old_on = self._as_bool(old_state.state) if old_state else None
        if old_on is None:
            # No valid prior on/off state: this is startup state restoration or
            # an availability change (unknown/unavailable -> on/off), NOT a
            # button press. Ignoring it prevents spurious clicks on restart.
            return
        if old_on == new_on:
            # Not a real transition (e.g. an attribute-only change).
            return

        if self._physical_only and self._is_ha_initiated(event.context):
            # The change was triggered by a Home Assistant user/automation, not
            # a physical press. Skip it when the mapping wants physical only.
            _LOGGER.debug(
                "button_actions '%s' ignoring HA-initiated change of %s",
                self._name,
                self._entity_id,
            )
            return

        self._detector.handle_transition(new_on)

    @staticmethod
    def _is_ha_initiated(context: Optional[Context]) -> bool:
        """True if a HA user or automation/script caused the change.

        A genuine device (physical) change carries a fresh context with no
        user and no parent; UI/automation/script changes set one of these.
        """
        if context is None:
            return False
        return context.user_id is not None or context.parent_id is not None

    def _schedule(self, delay_s: float, cb: Callable[[], None]) -> Callable[[], None]:
        """Arm a one-shot timer; return a cancel callable for the detector.

        The fired action must be a @callback so Home Assistant runs it on the
        event loop. A plain function would be dispatched to a worker thread,
        making the downstream hass.bus.async_fire / script run thread-unsafe.
        """

        @callback
        def _fire(_now: Any) -> None:
            cb()

        return async_call_later(self.hass, delay_s, _fire)

    @callback
    def _on_gesture(self, gesture: str) -> None:
        _LOGGER.debug("button_actions '%s' detected %s", self._name, gesture)

        if self._fire_events:
            self.hass.bus.async_fire(
                EVENT_GESTURE,
                {
                    ATTR_ENTITY_ID: self._entity_id,
                    ATTR_GESTURE: gesture,
                    ATTR_NAME: self._name,
                },
            )

        script = self._scripts.get(gesture)
        if script is not None:
            self.hass.async_create_task(
                script.async_run(context=Context()),
                name=f"{DOMAIN} {self._name} {gesture}",
            )
