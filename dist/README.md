# Animation Tool Kit (ATK) Toolbar

Animation Tool Kit (ATK) Toolbar is a dockable Maya toolbar that installs and launches a curated set of animation, rigging, viewport, and pipeline tools.

Version **1.1.12** fixes Maya locking up and crashing when you switch
workspaces and then relaunch the toolbar from the ATK shelf button. That was a
regression in 1.1.11. It keeps the 1.1.11 exit-crash fix and everything from
1.1.10, including **Timeline Ticks**: a compact yellow/red/blue palette for
classifying existing keys as Key, Extreme, Breakdown or Inbetween.
See [release notes](Animation_Tool_Kit_v1.1.12_Release_Notes.md).

For an existing video, use **Output → Destination → Force overwrite existing
output**, or choose a different filename. Failed encoding preserves the old video.

Video export requires an FFmpeg build with the chosen codec; **libx264** is the
recommended H.264 software fallback on Windows, macOS, and Linux. Choose the
executable in Settings. Maya itself and a working viewport are required to capture.

## What the installer does

When you drag-and-drop `install_atk_toolbar.mel` into Maya, the installer:

- Copies the `atk_toolbar` Python package into your Maya user scripts directory.
- Copies tool scripts from `animation tool kit scripts/` into your Maya user scripts directory.
- Copies tool icons into your Maya user icons directory.
- Adds an **ATK** shelf button to launch the toolbar.
- Launches the toolbar immediately after install.

## Folder layout for distribution

Keep these items side-by-side in the same folder before sending to users:

- `install_atk_toolbar.mel`
- `atk_toolbar/`
- `animation tool kit scripts/`

For **User Directory Check**, the installer first looks for:

- `animation tool kit scripts/User-Directory-Check/user_directory_check_icon.png`

If that file is missing, it falls back to:

- `icon/user_directory_check_icon.png`

## Installation steps (for artists)

1. Open Maya.
2. Drag `install_atk_toolbar.mel` from Explorer/Finder into the Maya viewport.
3. Wait for the install confirmation dialog.
4. Use the new **ATK** shelf button to open the toolbar.

## Notes

- **Timeline Ticks** provides a compact Key / Extreme / Breakdown / Inbetween
  window, plus a single-slot yellow/red/blue palette and menu on the main ATK
  toolbar. Labels follow key moves and deletions, including Add/Remove Frames
  and Undo/Redo while tracking is active. The window also includes green. Install using
  the usual ATK installer, then launch it from the timing group. See its
  [usage and limitations](animation%20tool%20kit%20scripts/Timeline_Ticks_1_0_0/README.md).

- The installer copies files into Maya user preference/script locations (per-user install).
- If a tool file or icon is missing, Maya will show a warning and continue installing the rest.
