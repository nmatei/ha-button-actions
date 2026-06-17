"""Unit tests for the pure GestureDetector state machine.

These run without a Home Assistant runtime: timers are driven by a fake
scheduler with a manual clock.
"""

from __future__ import annotations

import pytest

from button_actions.const import (
    GESTURE_DOUBLE,
    GESTURE_LONG,
    GESTURE_SINGLE,
)
from button_actions.gesture import GestureDetector

WINDOW = 0.6
LONG = 1.2


class FakeScheduler:
    """A manual-clock scheduler matching the schedule(delay, cb) -> cancel API."""

    def __init__(self) -> None:
        self.now = 0.0
        self._timers: list[list] = []  # [fire_at, cb, active]

    def schedule(self, delay, cb):
        timer = [self.now + delay, cb, True]
        self._timers.append(timer)

        def cancel():
            timer[2] = False

        return cancel

    def advance(self, dt):
        """Advance the clock and fire any timers that come due."""
        target = self.now + dt
        while True:
            due = [t for t in self._timers if t[2] and t[0] <= target]
            if not due:
                break
            due.sort(key=lambda t: t[0])
            timer = due[0]
            self.now = timer[0]
            timer[2] = False
            timer[1]()
        self.now = target


def make_detector(active, *, transitions_per_click=2):
    sched = FakeScheduler()
    gestures: list[str] = []
    detector = GestureDetector(
        transitions_per_click=transitions_per_click,
        click_window_s=WINDOW,
        long_press_time_s=LONG,
        active_gestures=set(active),
        on_gesture=gestures.append,
        schedule=sched.schedule,
    )
    return detector, sched, gestures


def press_momentary(detector):
    """One momentary press: OFF->ON->OFF (2 transitions)."""
    detector.handle_transition(True)
    detector.handle_transition(False)


# -- momentary mode -----------------------------------------------------------


def test_momentary_single_only_fires_immediately():
    detector, sched, gestures = make_detector({GESTURE_SINGLE})
    press_momentary(detector)
    # No double of interest -> classified on release, no waiting.
    assert gestures == [GESTURE_SINGLE]


def test_momentary_single_with_double_waits_for_window():
    detector, sched, gestures = make_detector({GESTURE_SINGLE, GESTURE_DOUBLE})
    press_momentary(detector)
    assert gestures == []  # still waiting for a possible second press
    sched.advance(WINDOW)
    assert gestures == [GESTURE_SINGLE]


def test_momentary_double_fires_once_count_reached():
    detector, sched, gestures = make_detector({GESTURE_SINGLE, GESTURE_DOUBLE})
    press_momentary(detector)
    sched.advance(WINDOW / 3)
    press_momentary(detector)
    # Second press reaches the highest gesture of interest -> immediate double.
    assert gestures == [GESTURE_DOUBLE]


def test_momentary_two_slow_presses_are_two_singles():
    detector, sched, gestures = make_detector({GESTURE_SINGLE, GESTURE_DOUBLE})
    press_momentary(detector)
    sched.advance(WINDOW)  # window closes -> single
    press_momentary(detector)
    sched.advance(WINDOW)  # second window closes -> single
    assert gestures == [GESTURE_SINGLE, GESTURE_SINGLE]


def test_momentary_long_press_fires_and_swallows_release():
    detector, sched, gestures = make_detector({GESTURE_SINGLE, GESTURE_LONG})
    detector.handle_transition(True)  # press and hold
    sched.advance(LONG)
    assert gestures == [GESTURE_LONG]
    detector.handle_transition(False)  # release is swallowed
    assert gestures == [GESTURE_LONG]
    # A fresh single press still works afterwards.
    press_momentary(detector)
    assert gestures == [GESTURE_LONG, GESTURE_SINGLE]


def test_momentary_quick_release_does_not_long_press():
    detector, sched, gestures = make_detector({GESTURE_SINGLE, GESTURE_LONG})
    press_momentary(detector)  # released before long timer
    sched.advance(WINDOW)
    sched.advance(LONG)
    assert gestures == [GESTURE_SINGLE]


# -- toggle mode --------------------------------------------------------------


def test_toggle_single_only_fires_immediately():
    detector, sched, gestures = make_detector(
        {GESTURE_SINGLE}, transitions_per_click=1
    )
    detector.handle_transition(True)  # one transition == one press
    assert gestures == [GESTURE_SINGLE]


def test_toggle_double_within_window():
    detector, sched, gestures = make_detector(
        {GESTURE_SINGLE, GESTURE_DOUBLE}, transitions_per_click=1
    )
    detector.handle_transition(True)
    assert gestures == []
    detector.handle_transition(False)
    assert gestures == [GESTURE_DOUBLE]


def test_toggle_single_when_double_active_but_no_second_press():
    detector, sched, gestures = make_detector(
        {GESTURE_SINGLE, GESTURE_DOUBLE}, transitions_per_click=1
    )
    detector.handle_transition(True)
    sched.advance(WINDOW)
    assert gestures == [GESTURE_SINGLE]


# -- mapping / interest -------------------------------------------------------


def test_double_press_with_only_single_active_maps_down_to_single():
    detector, sched, gestures = make_detector({GESTURE_SINGLE})
    press_momentary(detector)
    assert gestures == [GESTURE_SINGLE]  # fired on first press already
    press_momentary(detector)
    assert gestures == [GESTURE_SINGLE, GESTURE_SINGLE]


def test_no_active_gestures_never_fires():
    detector, sched, gestures = make_detector(set())
    press_momentary(detector)
    sched.advance(WINDOW)
    sched.advance(LONG)
    assert gestures == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
