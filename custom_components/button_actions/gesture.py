"""Pure gesture-detection state machine for Button Actions.

This module is deliberately free of any Home Assistant imports so it can be
unit-tested in isolation. Timers and gesture dispatch are injected as callables:

* ``schedule(delay_seconds, callback) -> cancel`` arms a one-shot timer and
  returns a callable that cancels it. The controller wires this to HA's
  ``async_call_later``; tests pass a fake scheduler with a manual clock.
* ``on_gesture(gesture)`` is invoked with one of the ``GESTURE_*`` constants
  when a gesture is classified.

The detector turns ON/OFF state transitions into gestures using a
time-window + transition-count model, and only ever waits for gestures the
caller marked as *active* (the "don't wait" optimization).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from .const import (
    GESTURE_CLICK_COUNT,
    GESTURE_LONG,
)

ScheduleCallback = Callable[[float, Callable[[], None]], Callable[[], None]]
GestureCallback = Callable[[str], None]


class GestureDetector:
    """Classify ON/OFF transitions into single/double/long-press gestures."""

    def __init__(
        self,
        *,
        transitions_per_click: int,
        click_window_s: float,
        long_press_time_s: float,
        active_gestures: set[str],
        on_gesture: GestureCallback,
        schedule: ScheduleCallback,
    ) -> None:
        """Initialize the detector.

        ``active_gestures`` is the set of gestures that are of interest (have an
        action configured and/or events are enabled). The detector uses it to
        decide how long to wait before classifying.
        """
        self._transitions_per_click = max(1, transitions_per_click)
        self._click_window_s = click_window_s
        self._long_press_time_s = long_press_time_s
        self._active_gestures = set(active_gestures)
        self._on_gesture = on_gesture
        self._schedule = schedule

        # Highest click-count gesture we care about (1=single, 2=double, 0=none).
        self._max_active_clicks = max(
            (
                GESTURE_CLICK_COUNT[g]
                for g in self._active_gestures
                if g in GESTURE_CLICK_COUNT
            ),
            default=0,
        )
        self._long_active = GESTURE_LONG in self._active_gestures

        self._transitions = 0
        self._window_cancel: Optional[Callable[[], None]] = None
        self._long_cancel: Optional[Callable[[], None]] = None
        # The click window has elapsed but classification was deferred because a
        # long-press timer is still pending (the input is being held).
        self._window_elapsed = False
        # True after a long press fires: swallow transitions until input rests.
        self._consumed_until_rest = False

    # -- public API -----------------------------------------------------------

    def handle_transition(self, is_on: bool) -> None:
        """Feed one genuine ON/OFF transition into the state machine.

        ``is_on`` is True for an OFF->ON (rising) edge, False for ON->OFF.
        """
        if self._consumed_until_rest:
            # A long press already fired for this hold; wait for the input to
            # return to its rest (OFF) state, then start fresh.
            if not is_on:
                self._reset()
            return

        # Any new transition cancels a pending long-press arm.
        self._cancel_long()

        if self._transitions == 0 and self._max_active_clicks >= 1:
            self._start_window()

        self._transitions += 1

        # Arm long press on a rising edge while the input is held.
        if is_on and self._long_active:
            self._long_cancel = self._schedule(
                self._long_press_time_s, self._fire_long_press
            )

        if self._window_elapsed:
            # Window already expired (we were waiting on a held long press).
            # A completed press (falling edge) classifies now.
            if not is_on:
                self._classify()
        else:
            self._maybe_classify_early()

    def cancel(self) -> None:
        """Cancel all timers and reset (used on teardown)."""
        self._reset()

    # -- internals ------------------------------------------------------------

    @property
    def _presses(self) -> int:
        return self._transitions // self._transitions_per_click

    def _maybe_classify_early(self) -> None:
        """Classify immediately once the highest gesture of interest is reached."""
        if self._max_active_clicks and self._presses >= self._max_active_clicks:
            self._classify()

    def _on_window_timeout(self) -> None:
        self._window_cancel = None
        if self._long_cancel is not None:
            # A long press is still pending (input held); defer classification
            # until the input is released or the long press fires.
            self._window_elapsed = True
            return
        self._classify()

    def _classify(self) -> None:
        """Pick the best matching active gesture for the presses counted."""
        presses = self._presses
        gesture: Optional[str] = None
        best = 0
        for candidate in self._active_gestures:
            count = GESTURE_CLICK_COUNT.get(candidate)
            if count is not None and best < count <= presses:
                best = count
                gesture = candidate

        self._reset()
        if gesture is not None:
            self._on_gesture(gesture)

    def _fire_long_press(self) -> None:
        self._long_cancel = None
        self._cancel_window()
        self._window_elapsed = False
        self._consumed_until_rest = True
        self._transitions = 0
        self._on_gesture(GESTURE_LONG)

    def _start_window(self) -> None:
        self._cancel_window()
        self._window_elapsed = False
        self._window_cancel = self._schedule(
            self._click_window_s, self._on_window_timeout
        )

    def _cancel_window(self) -> None:
        if self._window_cancel is not None:
            self._window_cancel()
            self._window_cancel = None

    def _cancel_long(self) -> None:
        if self._long_cancel is not None:
            self._long_cancel()
            self._long_cancel = None

    def _reset(self) -> None:
        self._cancel_window()
        self._cancel_long()
        self._transitions = 0
        self._window_elapsed = False
        self._consumed_until_rest = False
