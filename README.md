# Button Actions

A Home Assistant custom integration (HACS-compatible) that turns ON/OFF state
changes of any entity into **button gestures** — single click, double click,
long press — and maps each gesture to actions and/or events.

It is built for setups like a **Shelly Mini Gen 4** wired to a physical wall
switch that should "toggle" some lights (e.g. Tapo LED strips). Instead of
writing two brittle automations per gesture (one for `off-on`, one for `on-off`,
with `delay` + state-condition hacks), you describe each room **once** — in
YAML or in the UI.

## How it works

A click is not a state — it's a number of **ON/OFF transitions within a time
window**:

| Input mode  | One press is…              | Single click  | Double click  |
|-------------|----------------------------|---------------|---------------|
| `momentary` | `OFF→ON→OFF` (pulses back)  | 2 transitions | 4 transitions |
| `toggle`    | `OFF→ON` (state holds)      | 1 transition  | 2 transitions |

The detector only ever waits for gestures you actually configured (the
**"don't wait"** optimization):

- If only a single-click action is set, it fires **immediately** on the press —
  no waiting for a possible double.
- If no long-press action is set, the long-press timer is never armed.

Long press fires the moment the hold exceeds `long_press_time` and cancels click
detection. It is reliable in `momentary` mode; in `toggle` mode it is
best-effort (it measures how long the input stays in the ON state).

## Installation

### Option A — HACS (custom repository)

> Requires [HACS](https://hacs.xyz). The repo must be on GitHub (HACS installs
> from a Git URL).

1. Home Assistant → **HACS**.
2. **⋮** (top-right) → **Custom repositories**.
3. **Repository:** `https://github.com/nmatei/ha-button-actions`
   · **Type:** **Integration** → **Add**.
4. Back in HACS, search **Button Actions** → open it → **Download**.
5. **Restart Home Assistant** (Settings → System → Restart).

### Option B — Manual

1. Copy `custom_components/button_actions/` into `config/custom_components/`.
2. **Restart Home Assistant.**

## Configuration

You can configure mappings via the **UI** or **YAML** (mix freely).

### UI (Settings → Devices & Services → + Add Integration → Button Actions)

After choosing the integration you pick how to enter the mapping:

- **Guided** — fields for trigger entity, mode, timeouts, fire-events, plus a
  light/target picker per gesture. Each gesture also has an *advanced YAML
  action* field for scenes/scripts/etc., which overrides the picker.
- **YAML** — the whole mapping as one YAML object (same shape as below), so you
  can paste/copy/tweak it in one place.

Use **Configure** on an existing entry to edit it the same way (the form/YAML is
prefilled with the current config; the trigger entity can be changed too).

### YAML (`configuration.yaml`)

```yaml
button_actions:
  - name: Laurentiu
    trigger_entity: switch.shelly_laurentiu_input
    mode: momentary            # momentary | toggle
    click_window: 600          # ms, default 600
    long_press_time: 1200      # ms, default 1200 (only armed if long press configured)
    fire_events: true          # also fire button_actions_gesture events

    single_click_action:       # any standard HA action sequence (optional)
      - service: light.toggle
        target:
          entity_id:
            - light.tapo_strip_1
            - light.tapo_strip_2
    double_click_action:       # optional
      - service: scene.turn_on
        target: { entity_id: scene.movie }
    long_press_action: []      # optional
```

Copy the block for each room and change the entity ids. A full example with two
rooms and event automations is in
[examples/button_actions.yaml](examples/button_actions.yaml).

After editing YAML, call the **`button_actions.reload`** service (Developer
Tools → Actions) — no restart needed.

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `trigger_entity` | — | The `switch` / `binary_sensor` / etc. to watch (required) |
| `name` | trigger entity | Label used in logs and events |
| `mode` | `momentary` | `momentary` (2 transitions/press) or `toggle` (1/press) |
| `transitions_per_click` | by mode | Advanced override of transitions per press |
| `click_window` | `600` | ms to collect transitions after the first one |
| `long_press_time` | `1200` | ms hold to trigger long press |
| `fire_events` | `false` | Also fire `button_actions_gesture` events |
| `single_click_action` / `double_click_action` / `long_press_action` | — | Action sequences to run |

## Events

With `fire_events: true`, each gesture fires a `button_actions_gesture` event:

```yaml
event_type: button_actions_gesture
data:
  entity_id: switch.shelly_laurentiu_input
  gesture: double_click        # single_click | double_click | long_press
  name: Laurentiu
```

Wire custom behavior with a single automation per device:

```yaml
automation:
  - alias: Laurentiu double click → movie scene
    trigger:
      - platform: event
        event_type: button_actions_gesture
        event_data:
          entity_id: switch.shelly_laurentiu_input
          gesture: double_click
    action:
      - service: scene.turn_on
        target: { entity_id: scene.laurentiu_movie }
```

## Development / testing

The gesture state machine is pure Python (no HA import) and unit-tested:

```bash
python -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -v
```

CI runs hassfest, HACS validation, and these tests
([.github/workflows/validate.yml](.github/workflows/validate.yml)).
