"""Runtime controller that binds a trigger entity to gesture actions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Optional

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Context, Event, HomeAssistant, callback
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
    CONF_SINGLE_CLICK_ACTION,
    CONF_TRANSITIONS_PER_CLICK,
    CONF_TRIGGER_ENTITY,
    DEFAULT_CLICK_WINDOW,
    DEFAULT_FIRE_EVENTS,
    DEFAULT_LONG_PRESS_TIME,
    DEFAULT_MODE,
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

        mode = config.get(CONF_MODE, DEFAULT_MODE)
        self._transitions_per_click: int = config.get(
            CONF_TRANSITIONS_PER_CLICK
        ) or TRANSITIONS_PER_CLICK_BY_MODE.get(mode, 2)

        self._click_window_s = config.get(CONF_CLICK_WINDOW, DEFAULT_CLICK_WINDOW) / 1000
        self._long_press_time_s = (
            config.get(CONF_LONG_PRESS_TIME, DEFAULT_LONG_PRESS_TIME) / 1000
        )

        # Build a Script per gesture that has an action sequence configured.
        self._scripts: dict[str, Script] = {}
        for gesture, key in _ACTION_KEYS.items():
            sequence = config.get(key)
            if sequence:
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
        if old_on == new_on:
            # Not a real transition (e.g. attribute-only change).
            return

        self._detector.handle_transition(new_on)

    def _schedule(self, delay_s: float, cb: Callable[[], None]) -> Callable[[], None]:
        """Arm a one-shot timer; return a cancel callable for the detector."""
        return async_call_later(self.hass, delay_s, lambda _now: cb())

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
