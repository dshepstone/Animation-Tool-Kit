# Animation Tool Kit v1.1.2

Animation Tool Kit (ATK) **v1.1.2** is now available.

This is a major quality release: six tools were rebuilt or significantly upgraded, toolbar buttons gained one-click quick actions, three tools gained Maya hotkey support, and a toolkit-wide audit fixed installer text corruption, event-callback leaks, and distribution bloat across the whole package.

---

## Release information

- **Version:** 1.1.2
- **Package:** `Animation-Tool-Kit_v1_1_2.zip`
- **Type:** Production release
- **Platform:** Autodesk Maya 2022+ (Maya 2025+ recommended)
- **Install method:** Drag-and-drop `install_atk_toolbar.mel` into Maya

---

## Highlights

### One-click toolbar actions
- **AnimSnap** — left-click the toolbar button to snap the first selected object to the second (all axes) instantly. Right-click for the full window, snap-translate/rotate-only actions, and hotkey setup.
- **Reset Tool** — left-click resets all transforms on the selection instantly. Right-click for the full window, individual translate/rotate/scale resets, and hotkey setup.

### Maya hotkey support
**Xform Copy Paste**, **AnimSnap**, and **Reset Tool** now include a "Setup / Edit Hotkeys..." dialog: click a field, press a key combination, Apply. Bindings are written to your Maya hotkey set (with locked `Maya_Default` handling), appear in the Hotkey Editor under *Custom Scripts*, and persist between sessions.

### Xform Copy Paste 2.0
- Rebuilt window in the ATK design language with a vertical scroll layout and color-coded status pill.
- Removed the phantom shelf modifier-click "hotkeys" that never existed; real hotkeys via the new setup dialog.
- Locked or connected channels (common on rig controls) no longer abort a paste — they skip with a warning.
- World-space scale now lands correctly on objects under scaled parents.

### Wire Shape Tool 2.0
- Shapes reorganized into **Primitives / Arrows & Direction / Rig Controls / Utility** sections with live search.
- 14 new rig-ready controller shapes: Diamond 3D, Triangle, Hexagon, Half Circle, Curved Arrow, Spin Arrows, Root, Gear, Pole Vector, Lollipop, Paddle, Foot, Eye Target, Flag.
- New **Offset Dummy** builder: a locator-style gizmo control wrapped in a configurable chain of offset groups (`name_ZERO > name_OFS1..n > name_CTRL`) for clean nulls, constraint targets, and layered offsets — plus a helper that wraps existing objects in matched offset groups without moving them.

### Smart Select Sets 2.5
- No more permanently empty "Uncategorized" box — category boxes only appear once they hold sets (or right after you create one).
- The create dialog now includes a set-name field, an existing-category dropdown, and an optional **new category** field.
- Right-click a selection button to **add it to a Maya shelf** as a self-contained button (works with the tool closed; Shift+click adds to selection), plus Duplicate Group, Copy Object List, and Remove from Selection.
- Full ATK restyle, validation caching for a faster filter, and scene-event callback leak fixes.

### SavePlus 2.0.5
- Fixed a duplicate `closeEvent` that leaked protected scene-event callbacks every time the tool was opened and closed.
- Removed leftover debug scaffolding that faked a "4 minutes since last save" reminder right after launch and hid file monitoring behind the reminders checkbox.
- Full ATK restyle with a primary Save Plus action, clear per-button explanations, and a quieter log.

### AnimSnap 1.1
- Rebuilt window in the ATK design language; snaps are a single undo step and locked channels skip safely.

---

## Toolkit-wide fixes

- **Installer text corruption fixed everywhere** — em dashes and other special characters in eight `.mel` installers rendered as garbage (`â€"`) on Windows; all installer dialogs, warnings, and titles are now clean ASCII, and the ATK install-complete dialog was rewritten with a clearer summary.
- **Stale embedded installers re-synced** — the Add/Remove Inbetweens and Inbetweener drag-and-drop installers embed a copy of the tool source that had drifted from the shipped `.py`; both now deliver identical code on either install path.
- **Event-callback leaks fixed** — SavePlus and Smart Select Sets no longer leave scene-open callbacks running after their windows close.
- **Deprecated Qt calls updated** (`exec_` → `exec`) across the toolbar, Playblast Creator, Inbetweener, and Reset Tool for PySide6 compatibility.
- **70 stale compiled bytecode files removed** from the package — these could shadow updated scripts after partial upgrades.
- All tool windows verified against the shared ATK visual style.

---

## Included tools

### Timing
- Inbetweener (v2.0.2)
- Add / Remove Frames (v1.0.2)
- Tangent Tools (v1.0.0)
- TweenMachine (v3.x)
- Noise Generator (v1.1.0)
- Xform Copy Paste (v2.0.0)
- Bookmarks (v0.1.0)

### Viewport
- Micro Manipulator (v1.0.0)
- Temp Pivot (v1.0.5)
- Onion Skin (v2.2.0)
- AnimSnap (v1.1.0)

### Rigging
- Wire Shape Tool (v2.0.0)
- Reset Tool (v2.0.1)
- Selection Set / Smart Select Sets (v2.5.0)
- Character Snapshot (v1.0.0)
- Mirror Controls (v2.3.1)

### Pipeline
- SavePlus (v2.0.5)
- Studio Library (v2.21.1)
- Playblast Creator (v2.0.4)
- User Directory Check (v1.0.0)

---

## Installation

1. Download `Animation-Tool-Kit_v1_1_2.zip` from the release assets.
2. Extract the archive.
3. In Maya, drag and drop `install_atk_toolbar.mel` into the viewport.
4. Confirm install when prompted.
5. Launch the toolbar from the new **ATK** shelf button.

Upgrading from a previous version: run the installer again — it replaces the toolbar package, purges stale cached scripts, and refreshes the shelf button automatically.
