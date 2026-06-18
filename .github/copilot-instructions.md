# Button Actions — project guide

## IDE rules sync

This file is kept in sync with the Copilot instructions:

| File | IDE |
|---|---|
| `CLAUDE.md` | Claude Code |
| `.github/copilot-instructions.md` | GitHub Copilot |

A `PostToolUse` hook (`.claude/settings.json` → `.claude/sync-rules-hook.sh`)
copies whichever of these two files was just edited over the other, so they
stay identical automatically. If you edit one outside Claude Code, run:

```bash
bash .claude/sync-rules.sh <path-to-the-file-you-edited>
```

## What this is

A Home Assistant **custom integration** (HACS-compatible), domain `button_actions`.
It converts ON/OFF state changes of a trigger entity into **button gestures**
(👆 single click, ✌️ double click, ⏱️ long press) and runs configured actions
and/or fires events — replacing brittle per-gesture automations.

Motivating setup: a **Shelly Mini Gen 4** wired to a physical wall switch that
should "toggle" some lights (e.g. Tapo strips), reused across many rooms.

## Core model

A click = **number of ON/OFF transitions within a time window**, not a state.

| `mode`      | one press is…             | single | double |
|-------------|---------------------------|--------|--------|
| `momentary` | `OFF→ON→OFF` (returns)     | 2 transitions | 4 |
| `toggle`    | `OFF→ON` (state holds)     | 1 transition  | 2 |

- **Window**: start on first transition, collect for `click_window` ms, classify.
- **"Don't wait" optimization**: only wait for gestures that are *active*
  (have an action, or `fire_events` is on). If only single is active it fires
  immediately; if long press isn't active its timer is never armed.
- **Long press**: held longer than `long_press_time`; fires immediately and
  cancels click detection. **Only works in `momentary` mode** — in `toggle`
  mode the state just holds, so it's disabled there (a single press would look
  like an endless hold).

## Architecture (`custom_components/button_actions/`)

- `gesture.py` — `GestureDetector`: a **pure**, HA-free state machine. Timers and
  dispatch are injected as callables so it's unit-testable with a fake clock.
  This is where transition→gesture logic lives. Keep it HA-import-free.
- `controller.py` — `ButtonActionController`: subscribes to the trigger entity's
  state changes, filters real transitions, drives the detector, runs actions
  (via `homeassistant.helpers.script.Script`) and fires events.
- `config_flow.py` — UI config + options flow. A **menu** chooses between
  **Guided** (fields + per-gesture target picker) and **YAML** (whole mapping as
  one object). Both validate through `MAPPING_SCHEMA`.
- `schema.py` — `MAPPING_SCHEMA` (shared by YAML setup and the config flow) and
  `mapping_title()` (the emoji entry-title summary).
- `__init__.py` — YAML setup (list under `button_actions:`), `button_actions.reload`
  service, and config-entry lifecycle. Refreshes each entry's title on setup.
- `const.py` — keys, defaults, gesture constants, event name.
- `brand/` — icon assets (`icon.png` 256, `icon@2x.png` 512, + `dark_` variants).
  HACS requires `brand/icon.png` **inside the integration dir** (here).

## Configuration

```yaml
button_actions:
  - name: Laurentiu
    trigger_entity: switch.shelly_laurentiu_input
    mode: momentary            # momentary | toggle
    click_window: 600           # ms
    long_press_time: 1200       # ms (momentary only)
    fire_events: true           # also fire button_actions_gesture
    physical_only: false        # ignore HA-initiated changes (see below)
    single_click_action: [...]  # standard HA action sequence
    double_click_action: [...]
    long_press_action: [...]
```

UI mirrors this; the guided form maps a target picker to a `homeassistant.toggle`
action. Events: `button_actions_gesture` with `{entity_id, gesture, name}`.

## Non-obvious rules / gotchas (learned the hard way)

- **Normalize actions before `Script`**: run `cv.SCRIPT_SCHEMA(sequence)` before
  constructing `Script`, or it raises `KeyError: 'service_template'`. YAML is
  pre-validated; UI/legacy data may be raw.
- **Timer callbacks must be `@callback`**: `async_call_later` runs a plain
  function in a worker thread → `hass.bus.async_fire`/script run off-loop and
  trip thread-safety. The fired action is wrapped in `@callback`.
- **Ignore startup/availability changes**: only count a transition when there's
  a valid prior on/off state (`old_on is not None`). Otherwise the restore on
  HA restart (`unknown → on/off`) fires a spurious click.
- **`physical_only`**: when set, ignore changes whose context has a `user_id` or
  `parent_id` (HA user/automation) — only genuine device presses count.
- **Guided form action removal**: when a gesture's target picker is empty, keep
  the existing action **only if it's not a simple toggle** (scenes/scripts the
  picker can't show). A cleared toggle is removed.
- **Long press only in `momentary`** (see Core model).

## Development

- Pure-logic tests (no HA needed):
  ```bash
  python -m venv .venv && .venv/bin/pip install pytest
  .venv/bin/python -m pytest tests/ -q
  ```
  `tests/test_gesture.py` drives `GestureDetector` with a fake scheduler; add a
  case here for any timing/classification change.
- CI (`.github/workflows/validate.yml`): hassfest + HACS validation + pytest.
- Bump `manifest.json` `version` for releases; HACS installs from the default
  branch (`master`). README images must use absolute `raw.githubusercontent.com`
  URLs (HACS doesn't resolve relative paths).

## Conventions

- Match existing async/HA patterns; keep `gesture.py` free of HA imports.
- Keep YAML and UI behavior identical — both go through `MAPPING_SCHEMA`.
- Update `tests/` and this guide when behavior changes.
