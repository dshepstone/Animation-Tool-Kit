# Toolbar layouts — plan (ATK 1.1.17)

The toolbar has almost 30 buttons. Docked along the bottom of Maya it is long
and often runs off the edge. 1.1.17 adds layout options so the bar fits: fewer
buttons, folded groups, more rows, alignment, icon size and an expert mode,
all picked in **Settings → Layout** and shown on the toolbar immediately.

## Goals

- Every option works on all four dock sides and when floating.
- **Full** stays the default: anyone upgrading sees the same toolbar as 1.1.16.
- Nothing that works today breaks: docking on every side, the workspace and
  exit crash fixes, Reload Scripts, the Timeline Ticks palette, right-click
  menus, quick left-click actions, the inline Inbetweener slider and frame
  stepper, and the ATK logo button.

## Architecture

### `atk_toolbar/atk_layout.py` — the layout engine (no Qt, no Maya)

Pure Python, so every decision is unit-tested without Maya or a display.

- `default_settings()`, `decode_settings(raw)`, `encode_settings(dict)`:
  the versioned layout JSON. Anything unreadable, an unknown version, a wrong
  type or an out-of-range value falls back to the default for that field;
  decoding never raises.
- `migrate_hidden(registry, hidden_ids)`: builds the first layout data from the
  old `atk_hidden_<id>` optionVars, so tools hidden before 1.1.17 stay hidden.
- `decode_usage(raw)`, `encode_usage(counts)`, `bump_usage(counts, tool_id)`:
  the versioned usage JSON.
- `rank_most_used(tool_ids, counts, order)`: launch count, ties broken by
  registry order.
- `plan_layout(registry, settings, usage, orientation, ...)` → `LayoutPlan`:
  - `lines`: 1–3 lists of items. Rows when the bar is horizontal, columns when
    it is vertical. Items are `tool`, `group` (a fold-out button with its
    tools), `more` (the More fold-out with the rest) and `sep`.
  - `align`: `start`, `center` or `end` (left/top, centre, right/bottom).
  - `icon_size`, `expert`, `spacing`, `button_pad`.
- `measure(plan, ...)`: the pixel length and thickness of the tool area, so the
  workspaceControl can be sized before the widgets exist (Maya needs the size
  when it creates the control).

Wrapping: the tools are split across the lines in order with about the same
number of button slots on each line. A separator is never left at the start
or end of a line. Tangent Tools counts as four slots (its three quick tangent
buttons sit next to it).

### Presets

| Preset | What shows on the bar |
| --- | --- |
| Full (default) | Every shown tool in registry order, with group separators. Same as 1.1.16. |
| Most used | The top N tools by launch count (N = 3–25, default 10), in registry order so buttons don't jump around, then a **More** button holding the rest. |
| Custom | The shown tools in the user's own order. Custom groups appear as fold-out buttons at their first tool's place. |
| Grouped | One button per group (Timing, Viewport, Rigging, Pipeline, then custom groups). Each group is set to **Open** (tools inline) or **Folded** (one button). Default: all folded. |

**Expert** is a toggle on top of any preset: smaller icons (one step down),
tighter spacing, no separators, group and More buttons show icons only.
Tooltips are kept.

The tool checklist (show/hide and order) applies to every preset: hidden tools
never appear, not even in More or a group. Order is used by Custom.

### Persistence (Maya optionVars)

- `atk_toolbar_layout` — JSON string, `{"version": 1, ...}`:
  `preset`, `expert`, `most_used_count`, `order` (all tool ids), `hidden`,
  `group_open` (`{group: bool}`), `custom_groups`
  (`[{"name", "tools", "open"}]`), `lines` (1–3).
- `atk_toolbar_usage` — JSON string, `{"version": 1, "counts": {id: int}}`.
- Icon size and alignment keep their existing optionVars
  (`atk_toolbar_icon_size`, `atk_toolbar_icon_alignment`) so there is one
  source of truth and older ATK versions still read them. Their controls move
  to the Layout tab. Export/Import carries them in the file.
- Migration: when `atk_toolbar_layout` does not exist, the old
  `atk_hidden_<id>` values seed `hidden`. Afterwards the Layout data is the
  source of truth; ATK also keeps writing `atk_hidden_<id>`, so going back to
  1.1.16 still shows the same tools.
- New tools added in a later release are appended to `order` (shown) and new
  registry groups default to folded. Unknown ids in stored data are dropped.
- No `exec`/`eval`: only `json.loads` with type checks.

### Usage tracking

`atk_loader.launch_tool_fn` is the one call every launch goes through: plain
clicks, quick left-click actions, right-click actions and the Timeline Ticks
colour strips. It bumps the tool's count unless called with `track=False`
(startup services, Reload Scripts reopening windows). The Tangent Tools quick
buttons count for Tangent Tools. Counting never raises and never blocks a
launch. The bar does not reorder while you work; Most used re-ranks the next
time the toolbar is built (opening Maya, Settings, Reload Scripts).

### Rendering (`atk_toolbar.py`)

`ATKToolbarWidget._build()` asks the engine for a plan and renders it:

- The head stays fixed: grip, Settings gear, ATK logo, then the frame stepper
  and the Inbetweener slider (horizontal) or the slider (vertical). With more
  than one line, the head stays on one side and the lines stack beside it.
- Each line is a box layout; alignment adds stretches before/after the line.
  The vertical bar keeps its scroll area.
- `group` and `more` items render as a `QToolButton`. Clicking opens a small
  frameless popup strip (`Qt.Popup`, so an outside click closes it) holding
  ordinary tool buttons built by the same `_make_tool_btn`, so each keeps its
  icon, tooltip, quick left-click action and right-click menu. The popup opens
  away from the nearest screen edge (above a bar at the bottom of Maya, to the
  right of a bar on the left, and so on) and wraps into a grid when long.
  A left-click on a tool closes it.
- Size helpers (`_calc_content_width/height`, `_horizontal_bar_height`,
  `_vertical_bar_width`) use `atk_layout.measure`, so docked clamping and
  floating fit account for rows and columns.

### Settings → Layout tab

Left: Preset, Expert, Most used count, Rows/Columns (1–3), Alignment, Icon
size, per-group Open/Folded, custom groups (New / Rename / Delete / tools),
Reset usage, Reset layout, Export…, Import….
Right: the tool checklist with drag and Up/Down reordering.

Changes on the Layout tab are saved and applied to the toolbar straight away
(a short timer batches rapid clicks). The old Tools tab keeps the inline
widget switches and points to the Layout tab for tools.

## Tests

- `tests/test_toolbar_layout.py` (pure Python, in CI): each preset, rows and
  columns, separators at line ends, alignment mapping, usage ties, bad and
  old JSON, migration from `atk_hidden_*`, export/import round trip,
  `measure`, hidden tools never shown anywhere.
- `tests/test_toolbar_layout_qt.py` (offscreen PySide6, fake `maya` modules):
  builds `ATKToolbarWidget` in every preset × horizontal/vertical × 1–3
  lines, checks button counts, fold-out popups hold the right tools, quick
  actions and right-click menus are wired, and usage is counted.
- `tests/check_toolbar_layouts_maya.py` (mayapy, run locally): opens the
  toolbar docked on each side in each preset, checks it builds, sizes and
  survives Reload Scripts.

## Release bookkeeping

Version 1.1.17 in `atk_toolbar/__init__.py`, `atk_toolbar.py`, the CI package
and release steps, release notes, README.
